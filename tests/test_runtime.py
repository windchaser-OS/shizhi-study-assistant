import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from study_app import runtime


class RuntimeTests(unittest.TestCase):
    def test_source_defaults_preserve_existing_workspace(self):
        with patch.object(sys, "frozen", False, create=True), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime.resource_root(), runtime.source_root())
            self.assertEqual(runtime.default_data_dir(), runtime.source_root() / ".study-data")
            self.assertEqual(runtime.default_vault(), runtime.source_root() / "obsidian" / "universities study program")

    def test_frozen_assets_and_user_data_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            # Resolve Windows TEMP aliases before constructing expected paths.
            root = Path(temporary).resolve()
            with (patch.object(sys, "frozen", True, create=True),
                  patch.object(sys, "_MEIPASS", str(root / "readonly-bundle"), create=True),
                  patch.dict(os.environ, {"LOCALAPPDATA": str(root / "user-profile")}, clear=True)):
                self.assertEqual(runtime.resource_root(), root / "readonly-bundle")
                self.assertEqual(runtime.default_data_dir(), root / "user-profile" / "ShizhiStudyAssistant" / "data")
                self.assertEqual(runtime.default_vault(), root / "user-profile" / "ShizhiStudyAssistant" / "vault")
                self.assertFalse(root.joinpath("readonly-bundle").exists())

    def test_environment_overrides_work_in_frozen_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(sys, "frozen", True, create=True), patch.dict(os.environ, {
                "STUDY_DATA_DIR": str(root / "custom-data"), "STUDY_VAULT": str(root / "custom-vault")
            }):
                self.assertEqual(runtime.default_data_dir(), root / "custom-data")
                self.assertEqual(runtime.default_vault(), root / "custom-vault")


if __name__ == "__main__":
    unittest.main()
