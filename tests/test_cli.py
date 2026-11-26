"""Startup settings are read once and passed to the CLI converter."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_landscaper import cli, config


class CliSettingsTests(unittest.TestCase):
    def test_ini_setting_reaches_converter_and_other_options_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="video-landscaper-cli-") as folder:
            path = Path(folder) / "VideoLandscaper.ini"
            for enabled in (False, True):
                with self.subTest(enabled=enabled):
                    path.write_text(
                        f"[Encoding]\nlegacy_tv_compatibility = {str(enabled).lower()}\n",
                        encoding="utf-8",
                    )
                    with patch.object(config, "default_config_path", return_value=path), \
                            patch.object(cli, "load_settings", wraps=config.load_settings) as load, \
                            patch.object(cli, "convert", return_value=Path("output.mp4")) as convert, \
                            redirect_stdout(io.StringIO()):
                        result = cli.main([
                            "input.mp4", "--crf", "12", "--preset", "fast",
                            "--max-width", "1280", "--audio-bitrate", "64k",
                        ])
                    self.assertEqual(result, 0)
                    load.assert_called_once_with()
                    options = convert.call_args.args[0]
                    self.assertEqual(options.legacy_tv_compatibility, enabled)
                    self.assertEqual(options.effective_crf, 20 if enabled else 12)
                    self.assertEqual(options.max_width, 1280)
                    self.assertEqual(options.preset, "fast")
                    self.assertEqual(options.audio_bitrate, "64k")

    def test_invalid_ini_reports_error_without_starting_conversion(self):
        with tempfile.TemporaryDirectory(prefix="video-landscaper-cli-") as folder:
            path = Path(folder) / "VideoLandscaper.ini"
            path.write_text("[Encoding]\nlegacy_tv_compatibility = perhaps\n", encoding="utf-8")
            errors = io.StringIO()
            with patch.object(config, "default_config_path", return_value=path), \
                    patch.object(cli, "convert") as convert, redirect_stderr(errors):
                result = cli.main(["input.mp4"])
            self.assertEqual(result, 1)
            self.assertIn(str(path), errors.getvalue())
            convert.assert_not_called()

    def test_help_does_not_read_or_create_configuration(self):
        with patch.object(cli, "load_settings") as load, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
