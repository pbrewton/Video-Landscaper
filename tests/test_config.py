"""Isolated checks for shared startup settings and safe default creation."""

from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_landscaper import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="video-landscaper-config-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.path = self.folder / "profile" / config.CONFIG_FILENAME

    def write(self, contents, *, encoding="utf-8"):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(contents, encoding=encoding)

    def test_missing_file_creates_editable_defaults_and_returns_disabled(self):
        settings = config.load_settings(self.path)
        self.assertFalse(settings.legacy_tv_compatibility)
        self.assertIn("[Encoding]", self.path.read_text(encoding="utf-8"))
        self.assertIn("legacy_tv_compatibility = false", self.path.read_text(encoding="utf-8"))

    def test_existing_file_is_preserved_and_returns_frozen_snapshot(self):
        contents = "; My custom settings\n[Encoding]\nlegacy_tv_compatibility = true\n"
        self.write(contents)
        before = self.path.read_bytes()
        timestamp = self.path.stat().st_mtime_ns
        settings = config.load_settings(self.path)
        self.assertTrue(settings.legacy_tv_compatibility)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mtime_ns, timestamp)
        self.write("[Encoding]\nlegacy_tv_compatibility = false\n")
        self.assertTrue(settings.legacy_tv_compatibility)
        self.assertFalse(config.load_settings(self.path).legacy_tv_compatibility)
        with self.assertRaises(FrozenInstanceError):
            settings.legacy_tv_compatibility = False

    def test_supported_boolean_spellings_and_utf8_bom(self):
        for value, expected in (("true", True), ("false", False), ("YES", True), ("OFF", False), ("1", True), ("0", False)):
            with self.subTest(value=value):
                self.write(f"[Encoding]\nlegacy_tv_compatibility = {value}\n", encoding="utf-8-sig")
                self.assertEqual(config.load_settings(self.path).legacy_tv_compatibility, expected)

    def test_missing_section_or_key_defaults_to_disabled(self):
        for contents in ("; Empty settings\n", "[Encoding]\n", "[Other]\nexample = 100%\n"):
            with self.subTest(contents=contents):
                self.write(contents)
                self.assertFalse(config.load_settings(self.path).legacy_tv_compatibility)

    def test_invalid_settings_report_the_file_without_rewriting_it(self):
        for contents in (
            "[Encoding]\nlegacy_tv_compatibility = perhaps\n",
            "[Encoding\nlegacy_tv_compatibility = true\n",
            "[Encoding]\nlegacy_tv_compatibility = true\nlegacy_tv_compatibility = false\n",
        ):
            with self.subTest(contents=contents):
                self.write(contents)
                before = self.path.read_bytes()
                with self.assertRaises(ValueError) as caught:
                    config.load_settings(self.path)
                self.assertIn(str(self.path), str(caught.exception))
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_encoding_identifies_file(self):
        self.write("[Encoding]\n")
        self.path.write_bytes(b"\xff\xfeinvalid")
        with self.assertRaisesRegex(ValueError, "UTF-8") as caught:
            config.load_settings(self.path)
        self.assertIn(str(self.path), str(caught.exception))

    def test_path_that_is_a_directory_reports_access_error(self):
        self.path.mkdir(parents=True)
        with self.assertRaises(OSError) as caught:
            config.load_settings(self.path)
        self.assertIn(str(self.path), str(caught.exception))

    def test_creation_race_does_not_replace_other_interfaces_settings(self):
        self.path.parent.mkdir(parents=True)
        original_open = Path.open

        def create_first(path, mode="r", *args, **kwargs):
            if path == self.path and mode == "x":
                self.write("[Encoding]\nlegacy_tv_compatibility = true\n")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", create_first):
            self.assertTrue(config.load_settings(self.path).legacy_tv_compatibility)

    def test_windows_uses_shared_roaming_profile_path(self):
        with patch.object(config.sys, "platform", "win32"), patch.dict(os.environ, {"APPDATA": str(self.folder)}):
            expected = self.folder / "VideoLandscaper" / config.CONFIG_FILENAME
            self.assertEqual(config.default_config_path(), expected)
            self.assertFalse(config.load_settings().legacy_tv_compatibility)
            self.assertTrue(expected.is_file())

    def test_windows_without_appdata_uses_roaming_profile_fallback(self):
        with patch.object(config.sys, "platform", "win32"), patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=self.folder):
            self.assertEqual(config.default_config_path(), self.folder / "AppData" / "Roaming" / "VideoLandscaper" / config.CONFIG_FILENAME)

    def test_other_platform_uses_xdg_or_home_config_folder(self):
        with patch.object(config.sys, "platform", "linux"), patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.folder)}):
            self.assertEqual(config.default_config_path(), self.folder / "VideoLandscaper" / config.CONFIG_FILENAME)
        with patch.object(config.sys, "platform", "linux"), patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=self.folder):
            self.assertEqual(config.default_config_path(), self.folder / ".config" / "VideoLandscaper" / config.CONFIG_FILENAME)


if __name__ == "__main__":
    unittest.main()
