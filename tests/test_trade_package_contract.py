"""Keep the installable plugin advertisement aligned with its native tools/skills."""
import json
from pathlib import Path
import re

from core.foreign_trade.tool_names import TRADE_TOOL_NAMES
from core.foreign_trade import diligence, communication, negotiation, procurement, listing, closing, retrospective

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "extensions/foreign_trade/plugin"
DEFAULT = ROOT / "src/backend/extensions/skills/default"


def test_advertised_native_tools_match_actual_dispatch_names():
    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    native = manifest["extensions"]["org.hugagent"]["x_foreign_trade"]["native_tools"]
    assert len(native) == len({tool["name"] for tool in native})
    assert {tool["name"] for tool in native} == TRADE_TOOL_NAMES


def test_every_workflow_stage_has_installable_skill_and_complete_relative_references():
    names = {name for module in (diligence, communication, negotiation, procurement, listing, closing, retrospective)
             for name in module.STAGES.values()}
    mirrored = names.copy()
    names.update({"buyer-inquiry-followup", "inquiry-quote", "product-content", "cross-role-collaboration", "localization-review", "trade-compliance-check"})
    for name in names:
        folder = PLUGIN / "skills" / name
        skill = folder / "SKILL.md"
        assert skill.is_file(), name
        if name in mirrored:
            assert (DEFAULT / name / "SKILL.md").is_file(), name
        text = skill.read_text()
        for relative in re.findall(r"\]\((references/[^)]+)\)", text):
            target = folder / relative
            assert target.is_file(), (name, relative)
            if target.suffix == ".json":
                assert isinstance(json.loads(target.read_text()), dict)
            if name in mirrored:
                assert (DEFAULT / name / relative).is_file(), (name, relative)

def test_compliance_adapter_keeps_local_lexicon_authority():
    text = (PLUGIN / "skills/trade-compliance-check/SKILL.md").read_text()
    assert "trade_review" in text and "localization-review" in text
    assert not (PLUGIN / "skills/trade-compliance-check/scripts").exists()
    for base in (PLUGIN / "skills", DEFAULT):
        assert not (base / "trade-sensitive-word-check").exists()
        assert (base / "trade-compliance-check/references/review-checklist.md").is_file()
        assert (base / "trade-compliance-check/SKILL.md").read_text() == text