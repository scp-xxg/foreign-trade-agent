"""Upgrade one stopped public CE SQLite installation in an isolated process.

The only backup is a private SQLite snapshot under the supplied app home. No
account rows, authentication values or configuration payloads are printed.
Restore is explicit and first retains the current database as another snapshot.
Stop the backend before upgrade/restore; this helper does not manage services.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def database_revision(database: Path) -> str | None:
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone():
            return None
        rows = db.execute('SELECT version_num FROM alembic_version').fetchall()
        if len(rows) > 1:
            raise RuntimeError('Multiple database migration heads; automatic upgrade refused.')
        return rows[0][0] if rows else None


def duplicate_identity_groups(database: Path) -> int:
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(users_shadow)')}
        if 'user_center_id' not in columns:
            return 0
        return db.execute("SELECT count(*) FROM (SELECT 1 FROM users_shadow WHERE user_center_id IS NOT NULL AND user_center_id <> '' GROUP BY user_center_id HAVING count(*) > 1)").fetchone()[0]


def legacy_site_row_count(database: Path) -> int:
    """Count only; never materialize the legacy submission or KV payloads."""
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        total = 0
        for name in ('site_kv', 'site_submissions'):
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone():
                total += db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
        return total


def preserve_legacy_chat_protocols(database: Path, revision: str | None, *, legacy_unversioned: bool = False) -> int:
    """Preserve the old transport without selecting provider config or credentials.

    Runs before upgrade/import, so only providers already present in an old
    versioned database can match. Repeated runs at the current head do nothing.
    """
    match = re.fullmatch(r'ce_(\d+)', revision or ('ce_0000' if legacy_unversioned else ''))
    if not match or int(match.group(1)) >= 34:
        return 0
    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(model_providers)')}
        if not {'provider_id', 'provider_type', 'extra_config'}.issubset(columns):
            return 0
        # Every JSON function sees valid JSON; invalid/non-object stored values
        # remain untouched. Existing explicit protocol choices also remain intact.
        from core.models.providers.registry import PROVIDER_SPECS
        excluded = tuple(spec.id for spec in PROVIDER_SPECS.values() if not spec.speaks_responses)
        vendor_scope = (' AND (provider IS NULL OR provider NOT IN (' + ','.join('?' for _ in excluded) + '))') if 'provider' in columns else ''
        safe = "CASE WHEN json_valid(extra_config) THEN extra_config ELSE '{}' END"
        obj = "CASE WHEN json_type(" + safe + ") = 'object' THEN " + safe + " ELSE '{}' END"
        result = db.execute("UPDATE model_providers SET extra_config=json_set(" + obj + ", '$.api_protocol', 'chat_completions') "
            "WHERE provider_type='chat' AND (extra_config IS NULL OR (json_valid(extra_config) AND json_type(" + safe + ") IN ('object','null'))) "
            "AND (json_type(" + obj + ", '$.api_protocol') IS NULL OR json_type(" + obj + ", '$.api_protocol') = 'null' "
            "OR (json_type(" + obj + ", '$.api_protocol') = 'text' AND trim(json_extract(" + obj + ", '$.api_protocol')) = ''))" + vendor_scope, excluded if 'provider' in columns else ())
        return result.rowcount


def duplicate_artifact_name_rows(database: Path) -> int:
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(artifacts)')}
        if not {'user_id', 'filename'}.issubset(columns):
            return 0
        folder = 'user_folder_id' if 'user_folder_id' in columns else 'NULL'
        live = 'deleted_at IS NULL AND ' if 'deleted_at' in columns else ''
        return db.execute('SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM artifacts WHERE ' + live +
            'user_id IS NOT NULL AND filename IS NOT NULL GROUP BY user_id,' + folder + ',filename HAVING count(*)>1)').fetchone()[0]


def repair_legacy_personal_filenames(database: Path, expected: int) -> int:
    """Use upstream naming/journal rules with a metadata-only SQL projection.

    No payload, credentials or file bytes are selected. Identity, ownership and
    every storage reference stay unchanged. The private snapshot reverses this.
    """
    from core.db.local_personal_file_upgrade import _replacement
    with sqlite3.connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in db.execute('PRAGMA table_info(artifacts)')}
        if not columns:
            if expected: raise RuntimeError('Artifact repair preflight changed.')
            return 0
        if not {'artifact_id','user_id','filename','title'}.issubset(columns):
            raise RuntimeError('Legacy artifacts schema lacks identity columns.')
        for name, kind in [('user_folder_id','VARCHAR(64)'),('deleted_at','DATETIME')]:
            if name not in columns: db.execute('ALTER TABLE artifacts ADD COLUMN ' + name + ' ' + kind)
        ordering = 'created_at,artifact_id' if 'created_at' in columns else 'artifact_id'
        rows = db.execute('SELECT artifact_id,user_id,user_folder_id,filename,title FROM artifacts WHERE deleted_at IS NULL AND user_id IS NOT NULL AND filename IS NOT NULL ORDER BY ' + ordering).fetchall()
        occupied = {(owner,folder,name) for _,owner,folder,name,_ in rows}
        folders = {row[1] for row in db.execute('PRAGMA table_info(user_folders)')}
        if {'user_id','parent_folder_id','name'}.issubset(folders):
            condition = ' WHERE deleted_at IS NULL' if 'deleted_at' in folders else ''
            occupied.update(db.execute('SELECT user_id,parent_folder_id,name FROM user_folders' + condition).fetchall())
        seen, changes = set(), []
        for identifier,owner,folder,name,title in rows:
            key = (owner,folder,name)
            if key not in seen:
                seen.add(key)
                continue
            replacement = _replacement(name,identifier,(owner,folder),occupied)
            next_title = replacement if title == name else title
            changes.append((identifier,name,title,replacement,next_title))
            occupied.add((owner,folder,replacement))
        if len(changes) != expected:
            raise RuntimeError('Artifact repair count changed after preflight; no filenames changed.')
        if changes:
            db.execute('CREATE TABLE IF NOT EXISTS personal_filename_repairs (artifact_id VARCHAR(64) PRIMARY KEY,old_filename VARCHAR(500) NOT NULL,old_title VARCHAR(500),new_filename VARCHAR(500) NOT NULL,new_title VARCHAR(500))')
            db.executemany('INSERT INTO personal_filename_repairs VALUES(?,?,?,?,?)',changes)
            db.executemany('UPDATE artifacts SET filename=?,title=? WHERE artifact_id=?',[(new_name,new_title,identifier) for identifier,_,_,new_name,new_title in changes])
        return len(changes)


def _snapshot(home: Path, label: str) -> Path:
    directory = home / 'upgrade-backups'
    if directory.is_symlink() or not directory.resolve().is_relative_to(home):
        raise RuntimeError('Backup directory must stay inside the supplied app home.')
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = directory / (stamp + '-' + label + '-' + uuid4().hex[:8] + '.db')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect((home / 'data.db').as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise RuntimeError('Recovery snapshot failed its integrity check.')
        target.chmod(0o600)
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _worker(home: Path, *, repair_filenames: bool = False, expected_repairs: int = 0) -> dict:
    # The parent launches a fresh interpreter with home-scoped environment before
    # any settings, engines or service singleton can be imported.
    os.umask(0o077)
    phase = 'environment'
    try:
        from cli import apply_local_env
        apply_local_env(3001)
        phase = 'legacy_filenames'
        repaired = repair_legacy_personal_filenames(home / 'data.db', expected_repairs) if repair_filenames else 0
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config(str(ROOT / 'alembic.ini'))
        config.set_main_option('script_location', str(ROOT / 'src/backend/alembic'))
        expected = ScriptDirectory.from_config(config).get_current_head()
        phase = 'alembic'
        command.upgrade(config, 'head')
        if database_revision(home / 'data.db') != expected:
            raise RuntimeError('Schema version does not match the source head.')
        phase = 'identity_preflight'
        if duplicate_identity_groups(home / 'data.db'):
            raise RuntimeError('Duplicate identities require manual reconciliation.')
        phase = 'schema_and_catalog'
        from hugagent_cli.schema import ensure_schema_and_seed
        ensure_schema_and_seed()
        phase = 'content_seed'
        from core.db.engine import SessionLocal
        from core.files.content.branding import seed_page_config_if_missing, enforce_ce_branding, backfill_navigation_entries
        from core.llm.prompt_versions import seed_from_filesystem
        with SessionLocal() as db:
            seed_page_config_if_missing(db)
            enforce_ce_branding(db)
            backfill_navigation_entries(db)
            seed_from_filesystem(db=db)
        return {'ok': True, 'revision': expected, 'legacy_filenames_repaired': repaired}
    except Exception as exc:
        # SQL exception text can contain row values; expose only phase and class.
        frames = traceback.extract_tb(exc.__traceback__)
        locations = [str(Path(frame.filename).resolve().relative_to(ROOT)) + ':' + str(frame.lineno) for frame in frames if Path(frame.filename).resolve().is_relative_to(ROOT) and '/.venv' not in frame.filename]
        status = getattr(exc, 'status_code', None)
        return {'ok': False, 'phase': phase, 'error_type': type(exc).__name__,
                'status': status if isinstance(status, int) else None, 'locations': locations[-5:]}


def prepare_database(home: Path, *, allow_create: bool = False, restore: Path | None = None, legacy_chat_completions: bool = False, repair_legacy_filenames: bool = False, expected_filename_repairs: int | None = None) -> dict:
    if sqlite3.sqlite_version_info < (3, 38, 0):
        raise RuntimeError('This schema requires SQLite 3.38+; select a newer Python/SQLite runtime before upgrading.')
    home = home.expanduser().resolve()
    database = home / 'data.db'
    if database.is_symlink():
        raise RuntimeError('Refusing a database symlink; choose its own app home.')
    existed = database.is_file()
    if not existed and (not allow_create or restore is not None):
        raise RuntimeError('Existing local data.db was not found; nothing changed.')
    if restore is not None:
        restore = restore.expanduser().resolve()
        backup_root = (home / 'upgrade-backups').resolve()
        if not restore.is_relative_to(backup_root) or not backup_root.is_relative_to(home) or not restore.is_file():
            raise RuntimeError('Restore must use an existing snapshot inside this app home.')
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(home / '.foreign-trade-upgrade.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another installation or upgrade is running for this app home.') from None
        snapshot = _snapshot(home, 'before-restore' if restore else 'before-upgrade') if existed else None
        previous = database_revision(database) if existed else None
        if restore is not None:
            with sqlite3.connect(restore.as_uri() + '?mode=ro', uri=True) as source:
                if source.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise RuntimeError('Snapshot integrity check failed; database not restored.')
                with sqlite3.connect(database) as target:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone() != ('ok',):
                        raise RuntimeError('Restored database failed its integrity check.')
            database.chmod(0o600)
            return {'ok': True, 'action': 'restored', 'revision': database_revision(database), 'backup': str(snapshot)}
        if existed and duplicate_identity_groups(database):
            raise RuntimeError(f'Duplicate identity groups require manual reconciliation; recovery snapshot: {snapshot}')
        if existed and legacy_site_row_count(database):
            raise RuntimeError(f'Legacy site storage contains data; automatic JSON export is not permitted. Recovery snapshot: {snapshot}')
        duplicate_names = duplicate_artifact_name_rows(database) if existed else 0
        if duplicate_names and not repair_legacy_filenames:
            raise RuntimeError(f'Legacy personal filenames conflict ({duplicate_names} extra rows); use explicit --repair-legacy-filenames after checking the reversible metadata-only repair. Recovery snapshot: {snapshot}')
        if expected_filename_repairs is not None and duplicate_names != expected_filename_repairs:
            raise RuntimeError(f'Expected {expected_filename_repairs} filename repairs but found {duplicate_names}; no repair applied. Recovery snapshot: {snapshot}')
        protocols_preserved = preserve_legacy_chat_protocols(database, previous, legacy_unversioned=legacy_chat_completions) if existed else 0
        from foreign_trade.team import runtime_env
        environment = runtime_env(home)
        environment['SITE_STORAGE_BACKUP_DIR'] = str(home / 'upgrade-backups/site-storage')
        environment['PYTHONPATH'] = str(ROOT / 'src/backend')
        environment['HUGAGENT_UPGRADE_WORKER'] = '1'
        command = [sys.executable, str(HERE / 'upgrade.py'), '--app-home', str(home), '--worker']
        if repair_legacy_filenames:
            command += ['--repair-legacy-filenames', '--expected-filename-repairs', str(duplicate_names)]
        try:
            result = subprocess.run(command,
                cwd=ROOT, env=environment, text=True, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'Schema upgrade timed out; recovery snapshot: {snapshot or "fresh installation"}') from None
        try:
            report = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            report = {'ok': False, 'phase': 'worker', 'error_type': 'WorkerFailure'}
        if result.returncode or not report.get('ok'):
            raise RuntimeError('Schema upgrade failed in ' + str(report.get('phase', 'worker')) +
                ' (' + str(report.get('error_type', 'WorkerFailure')) + ', status=' + str(report.get('status')) +
                ', source=' + ','.join(report.get('locations', [])) + '); recovery snapshot: ' + str(snapshot or 'fresh installation'))
        database.chmod(0o600)
        return {'ok': True, 'action': 'upgraded' if existed else 'initialized', 'from_revision': previous,
                'revision': report['revision'], 'backup': str(snapshot) if snapshot else None,
                'legacy_chat_protocols_preserved': protocols_preserved, 'legacy_filenames_repaired': report.get('legacy_filenames_repaired', 0)}
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-home', required=True, type=Path)
    parser.add_argument('--allow-create', action='store_true', help='Initialize a new empty app home; no account is created')
    parser.add_argument('--legacy-chat-completions', action='store_true', help='Explicitly identify a known old unversioned local database that used Chat Completions; do not use for an unknown/new database')
    parser.add_argument('--repair-legacy-filenames', action='store_true', help='Preserve duplicate historical files by renaming metadata only, using upstream naming and an in-database journal')
    parser.add_argument('--expected-filename-repairs', type=int, help='Refuse if the count differs from this reviewed number')
    parser.add_argument('--restore', type=Path, help='Restore an in-home snapshot; retain a pre-restore snapshot first')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if os.environ.get('HUGAGENT_UPGRADE_WORKER') != '1':
            raise SystemExit('Use the public upgrade entry point.')
        result = _worker(args.app_home.resolve(), repair_filenames=args.repair_legacy_filenames, expected_repairs=args.expected_filename_repairs or 0)
        print(json.dumps(result))
        return 0 if result['ok'] else 1
    try:
        report = prepare_database(args.app_home, allow_create=args.allow_create, restore=args.restore, legacy_chat_completions=args.legacy_chat_completions, repair_legacy_filenames=args.repair_legacy_filenames, expected_filename_repairs=args.expected_filename_repairs)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (RuntimeError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        # Only our deliberately bounded errors are displayed, never SQLite values.
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(json.dumps({'ok': False, 'error': detail}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
