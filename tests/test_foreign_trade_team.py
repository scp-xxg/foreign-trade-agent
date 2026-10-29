"""Deployment guardrails: prevent reusing a teammate's database or services."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import os
import json
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trade_team", ROOT / "extensions/foreign_trade/team.py")
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)


class TeamBootstrapTests(unittest.TestCase):
    def test_explicit_home_overrides_foreign_runtime_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "new-home"
            with patch.dict(os.environ, {
                "HUGAGENT_HOME": "/another/instance", "HUGAGENT_CAPS_ROOT": "/another/caps",
                "DATABASE_URL": "sqlite:////another/data.db", "STORAGE_PATH": "/another/storage",
                "FRONTEND_DIST_DIR": "/another/frontend", "SCRIPT_RUNNER_WORKSPACE": "/another/workspace",
            }):
                env = team.runtime_env(home)
            self.assertEqual(env["HUGAGENT_HOME"], str(home))
            self.assertEqual(env["DATABASE_URL"], "sqlite:///" + str(home / "data.db"))
            self.assertEqual(env["HUGAGENT_CAPS_ROOT"], str(home))
            self.assertEqual(env["STORAGE_PATH"], str(home / "storage"))
            self.assertEqual(env["SCRIPT_RUNNER_WORKSPACE"], str(home / "workspace"))
            self.assertEqual(env["HUGAGENT_SKIP_ENV_FILES"], "1")
            self.assertEqual(env["FRONTEND_DIST_DIR"], str(team.FRONTEND / "dist"))
            self.assertFalse(home.exists())

    def test_vite_node_version_boundary(self):
        for version in ("v20.19.0", "22.12.0", "v22.22.1", "24.0.0"):
            self.assertTrue(team.node_supported(version), version)
        for version in ("v18.20.0", "20.18.3", "21.5.0", "22.11.0", "garbage"):
            self.assertFalse(team.node_supported(version), version)

    def test_dry_run_never_creates_data_or_launches_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "do-not-create"
            with patch.object(team.subprocess, "run") as run, patch.object(team.os, "execve") as execute:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    for action in ("setup", "init", "install", "upgrade", "start", "check"):
                        self.assertEqual(team.main([action, "--dry-run", "--app-home", str(home), "--username", "teammate"]), 0)
                run.assert_not_called()
                execute.assert_not_called()
            self.assertFalse(home.exists())

    def test_quick_check_selects_unittest_only_and_preserves_python_for_frontend(self):
        selected_python = Path("/tmp/selected-public-venv/bin/python")
        home = Path("/tmp/not-used-by-quick-check")
        output = io.StringIO()
        with patch.object(team, "PYTHON", selected_python), patch.object(team, "run") as run:
            with redirect_stdout(output):
                team.check(argparse.Namespace(dry_run=False, running=False), team.runtime_env(home))
        calls = run.call_args_list
        python_calls = [call for call in calls if str(call.args[0][0]) == str(selected_python)]
        self.assertEqual(len(python_calls), 5)
        patterns = [call.args[0][call.args[0].index("-p") + 1] for call in python_calls]
        self.assertEqual(set(patterns), {
            "test_foreign_trade_engine.py", "test_foreign_trade_env_isolation.py",
            "test_foreign_trade_quote_identity.py", "test_foreign_trade_quote_presentation.py",
            "test_foreign_trade_team.py",
        })
        self.assertTrue(all("*" not in pattern and "collaboration" not in pattern for pattern in patterns))
        self.assertTrue(all(call.args[0][1:4] == ["-m", "unittest", "discover"] for call in python_calls))
        frontend_calls = [call for call in calls if call.args[0][0] == "npm"]
        self.assertEqual([call.args[0][-1] for call in frontend_calls], [
            "test:foreign-trade-quote", "test:foreign-trade-content-card",
            "test:foreign-trade-collaboration", "test:foreign-trade-content-mode",
        ])
        self.assertTrue(all(call.kwargs["env"]["FOREIGN_TRADE_TEST_PYTHON"] == str(selected_python)
                            for call in frontend_calls))
        self.assertEqual(len(calls), 9)
        self.assertIn("未运行完整 pytest", output.getvalue())
        self.assertIn("真实模型对话", output.getvalue())

    def test_start_refuses_existing_backend_before_starting_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / "data.db").touch()
            frontend = home / "frontend"
            (frontend / "dist").mkdir(parents=True)
            (frontend / "dist/index.html").write_text("<html></html>")
            with patch.object(team, "FRONTEND", frontend), patch.object(team, "port_open", return_value=True), patch.object(team, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "3001"):
                    team.start(argparse.Namespace(dry_run=False), home, team.runtime_env(home))
                run.assert_not_called()

    def test_start_refuses_uninitialized_home(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(team, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "init"):
                team.start(argparse.Namespace(dry_run=False), Path(temp), team.runtime_env(Path(temp)))
            run.assert_not_called()

    def test_installer_receives_home_prompt_and_account(self):
        with patch.object(team, "run") as run:
            home = Path("/tmp/team-home")
            team.install(home, "alice", team.runtime_env(home), True)
            command = [str(value) for value in run.call_args.args[0]]
            self.assertIn("--apply-homepage-copy", command)
            self.assertIn("--apply-assistant-prompt", command)
            self.assertEqual(command[command.index("--app-home") + 1], str(home))
            self.assertEqual(command[command.index("--username") + 1], "alice")

class IsolatedUpgradeTests(unittest.TestCase):
    @staticmethod
    def call_helper(home, *arguments):
        result = subprocess.run([sys.executable, str(ROOT / 'extensions/foreign_trade/upgrade.py'),
            '--app-home', str(home), *arguments], cwd=ROOT, text=True, capture_output=True, timeout=120)
        if result.returncode:
            raise AssertionError(result.stderr[-1000:] or 'isolated upgrade failed')
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_fresh_schema_seeds_copy_without_creating_any_account(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'fresh'
            report = self.call_helper(home, '--allow-create')
            self.assertEqual(report['revision'], 'ce_0034')
            self.assertIsNone(report['backup'])
            self.assertEqual(stat.S_IMODE((home / 'data.db').stat().st_mode), 0o600)
            with sqlite3.connect(home / 'data.db') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM users_shadow').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM local_users').fetchone()[0], 0)
                self.assertIn('user_center_id', {row[1] for row in db.execute('PRAGMA table_info(users_shadow)')})
                payload = json.loads(db.execute("SELECT payload FROM content_blocks WHERE id='page_config'").fetchone()[0])
                self.assertEqual(payload['branding']['product_name'], 'HugAgentOS')
                self.assertIn('协同', payload['branding']['hero_title'])
                self.assertFalse(payload['auth']['allow_register'])
                self.assertIn('trade_collaboration', payload['navigation']['sidebar_items'])

    def test_legacy_revision_preserves_owned_business_and_restores_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            self.call_helper(home, '--allow-create')
            with sqlite3.connect(home / 'data.db') as db:
                db.execute("UPDATE alembic_version SET version_num='ce_0012'")
                db.execute('DROP INDEX IF EXISTS idx_users_shadow_user_center_id')
                db.execute('DROP INDEX IF EXISTS uq_users_shadow_user_center_id')
                db.execute('ALTER TABLE users_shadow DROP COLUMN user_center_id')
                db.execute("INSERT INTO users_shadow(user_id,username,metadata) VALUES('test-owner','teammate',?)", (json.dumps({'role':'super_admin','preserve_marker':'synthetic-account'}),))
                db.execute("INSERT INTO foreign_trade_inquiries(inquiry_id,owner_user_id,revision,payload,created_at,updated_at) VALUES('inq_test','test-owner',7,?,'2026-10-28','2026-10-28')", (json.dumps({'title':'synthetic inquiry','retained':True}),))
            report = self.call_helper(home)
            snapshot = Path(report['backup'])
            self.assertTrue(snapshot.is_relative_to(home / 'upgrade-backups'))
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
            self.assertEqual(report['from_revision'],'ce_0012')
            self.assertEqual(report['revision'],'ce_0034')
            with sqlite3.connect(home / 'data.db') as db:
                self.assertIn('user_center_id',{row[1] for row in db.execute('PRAGMA table_info(users_shadow)')})
                self.assertEqual(db.execute("SELECT username FROM users_shadow WHERE user_id='test-owner'").fetchone()[0],'teammate')
                self.assertEqual(db.execute("SELECT owner_user_id,revision FROM foreign_trade_inquiries WHERE inquiry_id='inq_test'").fetchone(),('test-owner',7))
                self.assertTrue(json.loads(db.execute("SELECT payload FROM foreign_trade_inquiries WHERE inquiry_id='inq_test'").fetchone()[0])['retained'])
            restored = self.call_helper(home,'--restore',str(snapshot))
            self.assertEqual(restored['revision'],'ce_0012')
            self.assertNotEqual(restored['backup'],str(snapshot))
            with sqlite3.connect(home / 'data.db') as db:
                self.assertNotIn('user_center_id',{row[1] for row in db.execute('PRAGMA table_info(users_shadow)')})
                self.assertEqual(db.execute('SELECT count(*) FROM foreign_trade_inquiries').fetchone()[0],1)

    def test_duplicate_identity_preflight_retains_private_backup_and_refuses_mutation(self):
        from foreign_trade.upgrade import prepare_database
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            with sqlite3.connect(home / 'data.db') as db:
                db.execute('CREATE TABLE users_shadow(user_id TEXT, user_center_id TEXT)')
                db.executemany('INSERT INTO users_shadow VALUES(?,?)',[('test-a','synthetic-duplicate'),('test-b','synthetic-duplicate')])
            with self.assertRaisesRegex(RuntimeError,'Duplicate identity'):
                prepare_database(home)
            snapshots = list((home / 'upgrade-backups').glob('*.db'))
            self.assertEqual(len(snapshots),1)
            self.assertEqual(stat.S_IMODE(snapshots[0].stat().st_mode),0o600)
            with sqlite3.connect(home / 'data.db') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM users_shadow').fetchone()[0],2)

    def test_restore_cannot_read_outside_the_target_app_home(self):
        from foreign_trade.upgrade import prepare_database
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'app'; home.mkdir()
            with sqlite3.connect(home / 'data.db') as db: db.execute('CREATE TABLE sentinel(id INTEGER)')
            outside = Path(temp) / 'outside.db'; outside.touch()
            with self.assertRaisesRegex(RuntimeError,'inside this app home'):
                prepare_database(home,restore=outside)
            self.assertFalse((home / 'upgrade-backups').exists())

    def test_installer_uses_current_services_and_keeps_account_and_prior_prompts(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            self.call_helper(home,'--allow-create')
            with sqlite3.connect(home / 'data.db') as db:
                db.execute("INSERT INTO users_shadow(user_id,username,metadata) VALUES('test-owner','teammate',?)",(json.dumps({'role':'super_admin','preserve_marker':'synthetic-account'}),))
            command = [sys.executable,str(ROOT / 'extensions/foreign_trade/install.py'),'--app-home',str(home),'--username','teammate','--apply-homepage-copy','--apply-assistant-prompt']
            installed = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
            self.assertEqual(installed.returncode,0,installed.stderr[-1500:])
            with sqlite3.connect(home / 'data.db') as db:
                before = json.loads(db.execute("SELECT payload FROM content_blocks WHERE id='prompt_versions'").fetchone()[0])
                old_id = before['active']['system']
                old = next(v for v in before['versions'] if v['kind']=='system' and v['id']==old_id)
                for part in old['parts']:
                    if part['part_id']=='system/00_role': part['content']='Human-edited synthetic test role'
                db.execute("UPDATE content_blocks SET payload=? WHERE id='prompt_versions'",(json.dumps(before),))
            again = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
            self.assertEqual(again.returncode,0,again.stderr[-1500:])
            with sqlite3.connect(home / 'data.db') as db:
                after = json.loads(db.execute("SELECT payload FROM content_blocks WHERE id='prompt_versions'").fetchone()[0])
                preserved = next(v for v in after['versions'] if v['kind']=='system' and v['id']==old_id)
                self.assertEqual(next(p['content'] for p in preserved['parts'] if p['part_id']=='system/00_role'),'Human-edited synthetic test role')
                self.assertEqual(db.execute("SELECT count(*) FROM installed_plugins WHERE owner_user_id='test-owner' AND slug='foreign-trade-demo'").fetchone()[0],1)
                metadata = json.loads(db.execute("SELECT metadata FROM users_shadow WHERE user_id='test-owner'").fetchone()[0])
                self.assertEqual(metadata,{'role':'super_admin','preserve_marker':'synthetic-account'})
                self.assertEqual(db.execute('SELECT count(*) FROM local_users').fetchone()[0],0)
                self.assertTrue(any(v['id']=='default' and v['kind']=='system' for v in after['versions']))

    def test_legacy_protocol_patch_is_narrow_and_idempotent(self):
        from foreign_trade.upgrade import preserve_legacy_chat_protocols
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'data.db'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE model_providers(provider_id TEXT PRIMARY KEY,provider_type TEXT,extra_config TEXT)')
                db.executemany('INSERT INTO model_providers VALUES(?,?,?)',[
                    ('legacy','chat',json.dumps({'temperature':0.2,'context_length':12345})),
                    ('explicit','chat',json.dumps({'api_protocol':'responses','context_length':54321})),
                    ('embedding','embedding','{}'),('empty','chat',json.dumps({'api_protocol':' '})),
                    ('null-config','chat',None),('null-protocol','chat',json.dumps({'api_protocol':None})),
                    ('invalid-json','chat','invalid'),('list-config','chat','[]'),
                ])
            self.assertEqual(preserve_legacy_chat_protocols(database,'ce_0012'),4)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute("SELECT json_extract(extra_config,'$.api_protocol'),json_extract(extra_config,'$.temperature'),json_extract(extra_config,'$.context_length') FROM model_providers WHERE provider_id='legacy'").fetchone(),('chat_completions',0.2,12345))
                self.assertEqual(db.execute("SELECT json_extract(extra_config,'$.api_protocol') FROM model_providers WHERE provider_id='explicit'").fetchone()[0],'responses')
                self.assertIsNone(db.execute("SELECT json_extract(extra_config,'$.api_protocol') FROM model_providers WHERE provider_id='embedding'").fetchone()[0])
                db.execute("INSERT INTO model_providers VALUES('new','chat','{}')")
            self.assertEqual(preserve_legacy_chat_protocols(database,'ce_0034'),0)
            with sqlite3.connect(database) as db:
                self.assertIsNone(db.execute("SELECT json_extract(extra_config,'$.api_protocol') FROM model_providers WHERE provider_id='new'").fetchone()[0])
            self.assertEqual(preserve_legacy_chat_protocols(database,None),0)
            with sqlite3.connect(database) as db: db.execute("DELETE FROM model_providers WHERE provider_id='new'")
            self.assertEqual(preserve_legacy_chat_protocols(database,'ce_0012'),0)

    def test_nonempty_legacy_site_data_refuses_json_export(self):
        from foreign_trade.upgrade import prepare_database
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            with sqlite3.connect(home / 'data.db') as db:
                db.execute('CREATE TABLE site_submissions(payload TEXT)')
                db.execute("INSERT INTO site_submissions VALUES('synthetic data must stay in database')")
            with self.assertRaisesRegex(RuntimeError,'automatic JSON export is not permitted'):
                prepare_database(home)
            self.assertEqual(len(list((home / 'upgrade-backups').glob('*.db'))),1)
            self.assertEqual(list((home / 'upgrade-backups').rglob('*.json')),[])
            with sqlite3.connect(home / 'data.db') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM site_submissions').fetchone()[0],1)

    def test_fresh_init_without_tty_does_not_create_an_account(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            program = "from pathlib import Path; from foreign_trade.team import initialize; initialize(Path(__import__('sys').argv[1]), 'new-account')"
            result = subprocess.run([sys.executable,'-c',program,str(home)],cwd=ROOT,capture_output=True,text=True,timeout=120)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('交互终端',result.stderr)
            with sqlite3.connect(home / 'data.db') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM local_users').fetchone()[0],0)

    def test_known_unversioned_transport_requires_explicit_flag(self):
        from foreign_trade.upgrade import preserve_legacy_chat_protocols
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'data.db'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE model_providers(provider_id TEXT PRIMARY KEY,provider_type TEXT,extra_config TEXT)')
                db.execute("INSERT INTO model_providers VALUES('known-old','chat','{}')")
            self.assertEqual(preserve_legacy_chat_protocols(database,None),0)
            self.assertEqual(preserve_legacy_chat_protocols(database,None,legacy_unversioned=True),1)
            self.assertEqual(preserve_legacy_chat_protocols(database,None,legacy_unversioned=True),0)
            with sqlite3.connect(database) as db:
                db.execute("INSERT INTO model_providers VALUES('new-after-upgrade','chat','{}')")
            self.assertEqual(preserve_legacy_chat_protocols(database,'ce_0034',legacy_unversioned=True),0)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute("SELECT json_extract(extra_config,'$.api_protocol') FROM model_providers WHERE provider_id='known-old'").fetchone()[0],'chat_completions')
                self.assertIsNone(db.execute("SELECT json_extract(extra_config,'$.api_protocol') FROM model_providers WHERE provider_id='new-after-upgrade'").fetchone()[0])

    def test_duplicate_names_are_repaired_without_changing_identity_payload_or_bytes(self):
        from foreign_trade.upgrade import prepare_database, repair_legacy_personal_filenames, duplicate_artifact_name_rows
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); database = home / 'data.db'
            physical = home / 'original.bin'; physical.write_bytes(b'synthetic unchanged bytes')
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE artifacts(artifact_id TEXT PRIMARY KEY,user_id TEXT,user_folder_id TEXT,filename TEXT,title TEXT,deleted_at TEXT,created_at TEXT,payload TEXT,storage_key TEXT)')
                db.executemany('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)',[(f'id-{i}','owner',None,'same.txt','Human title' if i==2 else 'same.txt',None,str(i),'synthetic payload','original.bin') for i in range(3)])
            self.assertEqual(duplicate_artifact_name_rows(database),2)
            with self.assertRaisesRegex(RuntimeError,'--repair-legacy-filenames'): prepare_database(home)
            with self.assertRaisesRegex(RuntimeError,'count changed'): repair_legacy_personal_filenames(database,1)
            self.assertEqual(duplicate_artifact_name_rows(database),2)
            self.assertEqual(repair_legacy_personal_filenames(database,2),2)
            self.assertEqual(duplicate_artifact_name_rows(database),0)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute('SELECT artifact_id,user_id,payload,storage_key FROM artifacts ORDER BY artifact_id').fetchall(),[(f'id-{i}','owner','synthetic payload','original.bin') for i in range(3)])
                self.assertEqual(db.execute("SELECT filename FROM artifacts WHERE artifact_id='id-0'").fetchone()[0],'same.txt')
                self.assertEqual(db.execute("SELECT title FROM artifacts WHERE artifact_id='id-2'").fetchone()[0],'Human title')
                self.assertEqual(db.execute('SELECT count(*) FROM personal_filename_repairs').fetchone()[0],2)
            self.assertEqual(physical.read_bytes(),b'synthetic unchanged bytes')

    def test_native_azure_and_nonchat_providers_are_not_protocol_pinned(self):
        from foreign_trade.upgrade import preserve_legacy_chat_protocols
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'data.db'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE model_providers(provider_id TEXT PRIMARY KEY,provider_type TEXT,provider TEXT,extra_config TEXT)')
                db.executemany('INSERT INTO model_providers VALUES(?,?,?,?)',[
                    ('generic','chat','openai_compatible','{}'),('qwen','chat','qwen_compat','{}'),
                    ('unknown','chat','unknown-legacy-vendor','{}'),('empty','chat',None,'{}'),
                    ('azure','chat','azure_openai','{}'),('native','chat','anthropic','{}'),
                    ('audio','chat','audio_compatible','{}'),('embedding','embedding','openai_compatible','{}'),
                ])
            self.assertEqual(preserve_legacy_chat_protocols(database,'ce_0012'),4)
            with sqlite3.connect(database) as db:
                for ident in ('azure','native','audio','embedding'):
                    self.assertIsNone(db.execute("SELECT json_extract(extra_config,'$.api_protocol') FROM model_providers WHERE provider_id=?",(ident,)).fetchone()[0])

    def test_unsupported_sqlite_runtime_refuses_before_touching_home(self):
        from foreign_trade.upgrade import prepare_database
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'untouched'
            with patch('foreign_trade.upgrade.sqlite3.sqlite_version_info',(3,37,0)):
                with self.assertRaisesRegex(RuntimeError,'SQLite 3.38'):
                    prepare_database(home,allow_create=True)
            self.assertFalse(home.exists())


if __name__ == "__main__":
    unittest.main()