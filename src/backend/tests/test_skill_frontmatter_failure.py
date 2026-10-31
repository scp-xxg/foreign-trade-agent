"""Malformed marketplace metadata must be isolated during chat preflight."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from features.desktop.capabilities.dependency import Context, _parse_skill_definition
from features.desktop.capabilities.readiness import builtin_readiness


class SkillFrontmatterFailureTest(unittest.TestCase):
    def test_malformed_yaml_becomes_invalid_definition(self):
        body = '---\nname: Ad Copywriter\ndescription: "text"\n  unexpected continuation\n---\nbody'
        with self.assertRaisesRegex(ValueError, "invalid skill frontmatter"):
            _parse_skill_definition(body)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "SKILL.md").write_text(body, encoding="utf-8")
            result = builtin_readiness(
                SimpleNamespace(path=path, install_id="skill:builtin:broken"), Context()
            )
            self.assertFalse(result["ready"])
            self.assertEqual(result["errors"][0]["reason"], "definition_invalid")

    def test_valid_frontmatter_keeps_dependencies(self):
        self.assertEqual(
            _parse_skill_definition('---\nname: good\ndependencies: []\n---\nbody'),
            {"name": "good", "dependencies": []},
        )


if __name__ == "__main__":
    unittest.main()
