"""Canonical local plugin activations survive later turns without crossing owners."""

from types import SimpleNamespace

import pytest

from core.llm import plugin_loader

USER = "sticky-owner"


def _row(install_id, *, slug="trade", owner=None, source="builtin"):
    return SimpleNamespace(
        install_id=install_id,
        slug=slug,
        owner_user_id=owner,
        source=source,
    )


def _ids(tokens, rows):
    return [
        row.install_id
        for row in plugin_loader._local_sticky_selection(tokens, rows, user_id=USER)
    ]


@pytest.mark.parametrize("token", ["plugin:local:trade", "trade"])
@pytest.mark.parametrize("reverse", [False, True])
def test_canonical_local_and_legacy_slug_prefer_current_user(token, reverse):
    rows = [
        _row("trade@global"),
        _row("trade@other", owner="another-user"),
        _row("trade@sticky-owner", owner=USER, source="imported_codex"),
    ]
    assert _ids([token], list(reversed(rows)) if reverse else rows) == ["trade@sticky-owner"]


def test_legacy_exact_installation_id_keeps_its_identity():
    rows = [_row("trade@global"), _row("trade@sticky-owner", owner=USER)]
    assert _ids(["trade@global"], rows) == ["trade@global"]


@pytest.mark.parametrize("token", ["plugin:local:trade", "trade", "trade@other"])
def test_foreign_owner_cannot_be_selected(token):
    assert _ids([token], [_row("trade@other", owner="another-user")]) == []


def test_local_selection_can_restore_visible_global_installation():
    rows = [_row("trade@other", owner="another-user"), _row("trade@global")]
    assert _ids(["plugin:local:trade"], rows) == ["trade@global"]


def test_builtin_only_resolves_global_builtin_source():
    rows = [
        _row("trade@sticky-owner", owner=USER),
        _row("trade@imported-global", source="imported_codex"),
        _row("trade@builtin-global"),
    ]
    assert _ids(["plugin:builtin:trade"], rows) == ["trade@builtin-global"]
    assert _ids(["plugin:builtin:trade"], rows[:2]) == []


@pytest.mark.parametrize("token", ["plugin:cloud-account:trade", "plugin:local", "plugin:local:"])
def test_scoped_cloud_or_malformed_token_never_falls_back_to_local_row(token):
    # Even a local row with a colliding exact id/slug cannot absorb a cloud token.
    rows = [_row(token, slug=token, owner=USER), _row("trade@global")]
    assert _ids([token], rows) == []


def test_aliases_select_each_installation_once():
    rows = [_row("trade@sticky-owner", owner=USER)]
    assert _ids(["plugin:local:trade", "trade", "trade@sticky-owner"], rows) == [
        "trade@sticky-owner"
    ]


@pytest.fixture
def local_runtime(tmp_path, monkeypatch):
    import core.db.engine as dbe
    import core.config.catalog_resolver as resolver
    from core.db.models import InstalledPlugin
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'sticky.db'}")
    InstalledPlugin.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(dbe, "SessionLocal", sessions)
    with sessions() as db:
        db.add(InstalledPlugin(
            install_id="trade@sticky-owner",
            slug="trade",
            name="Synthetic trade plugin",
            owner_user_id=USER,
            source="imported_codex",
            component_ids={"skills": ["trade-skill"], "mcp": ["trade-mcp"]},
        ))
        db.commit()
    monkeypatch.setattr(plugin_loader, "load_activated_plugin_slugs", lambda chat_id: [
        "plugin:local:trade"
    ])
    monkeypatch.setattr(plugin_loader, "_cloud_sticky_selection", lambda *a, **kw: [])
    requested = []

    def allow_explicit(db, user_id, *, skill_ids=None, mcp_ids=None):
        requested.append((user_id, skill_ids, mcp_ids))
        return list(skill_ids or []), list(mcp_ids or []), [], []

    monkeypatch.setattr(resolver, "resolve_explicit_runtime_capabilities", allow_explicit)
    yield requested
    engine.dispose()


def test_resolver_restores_canonical_local_components_on_later_turn(local_runtime):
    sticky = plugin_loader.resolve_sticky_plugin_capabilities(user_id=USER, chat_id="chat")
    assert sticky.install_ids == ["trade@sticky-owner"]
    assert sticky.slugs == ["trade"]
    assert sticky.skill_ids == ["trade-skill"]
    assert sticky.mcp_ids == ["trade-mcp"]
    assert local_runtime == [(USER, ["trade-skill"], ["trade-mcp"])]


def test_resolver_keeps_component_availability_gate(local_runtime, monkeypatch):
    import core.config.catalog_resolver as resolver

    monkeypatch.setattr(
        resolver, "resolve_explicit_runtime_capabilities",
        lambda *a, **kw: ([], [], ["trade-skill"], ["trade-mcp"]),
    )
    sticky = plugin_loader.resolve_sticky_plugin_capabilities(user_id=USER, chat_id="chat")
    assert sticky.install_ids == ["trade@sticky-owner"]
    assert sticky.skill_ids == sticky.mcp_ids == []


def test_resolver_preserves_cloud_account_denial(local_runtime, monkeypatch):
    from core.capabilities.errors import PermissionDenied

    def reject_cloud(*args, **kwargs):
        raise PermissionDenied("saved plugin belongs to another cloud account")

    monkeypatch.setattr(plugin_loader, "load_activated_plugin_slugs", lambda chat_id: [
        "plugin:other-account:trade"
    ])
    monkeypatch.setattr(plugin_loader, "_cloud_sticky_selection", reject_cloud)
    with pytest.raises(PermissionDenied):
        plugin_loader.resolve_sticky_plugin_capabilities(user_id=USER, chat_id="chat")
    assert local_runtime == []
