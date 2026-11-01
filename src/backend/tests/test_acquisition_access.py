"""Acquisition must be discoverable before the frontend access gate can open it."""
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from features.workbench import catalog


class AcquisitionAccessTest(unittest.TestCase):
    def setUp(self):
        self.layout = {"revision": 1, "defaultPinned": [], "forced": [], "hidden": []}
        patches = [
            patch.object(catalog, "resolve_user_capabilities", return_value={"allowed_apps": [], "lab_enabled": False, "can_manage_users": False}),
            patch.object(catalog.policy, "read", return_value=self.layout),
            patch.object(catalog.origin, "current", return_value={}),
            patch.object(catalog.external, "items", return_value=[]),
            patch.object(catalog, "local_mode_enabled", return_value=False),
            patch("features.workbench.migration_compat.active", return_value=True),
            patch("features.workbench.plugin_catalog.items", return_value=[]),
        ]
        for context in patches:
            context.start()
            self.addCleanup(context.stop)

    def test_acquisition_is_listed_and_can_be_opened_by_member(self):
        items = catalog.directory(None, "member")["items"]
        self.assertIn("builtin:trade_buyers", {item["applicationKey"] for item in items})
        item = catalog.readable(None, "member", "builtin:trade_buyers")
        self.assertTrue(item["availability"]["available"])
        self.assertEqual(item["declaration"]["target"], {"kind": "builtin", "componentId": "trade_buyers"})

    def test_explicitly_hidden_acquisition_remains_inaccessible(self):
        self.layout["hidden"] = ["builtin:trade_buyers"]
        self.assertNotIn("builtin:trade_buyers", {item["applicationKey"] for item in catalog.directory(None, "member")["items"]})
        with self.assertRaises(HTTPException) as error:
            catalog.readable(None, "member", "builtin:trade_buyers")
        self.assertEqual(error.exception.status_code, 404)
