"""Checks for the converter API shared by the command line and batch GUI."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import imageio_ffmpeg

from video_landscaper import conversion


class ConversionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="video-landscaper-runtime-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    def make_source(self):
        source = self.root / "holiday.mp4"
        subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30", "-t", "1",
             "-c:v", "libx264", "-preset", "ultrafast", str(source)],
            check=True, capture_output=True,
        )
        return source

    def args(self, source):
        return conversion.ConversionOptions(
            input=source, max_width=320, max_height=180, preset="ultrafast",
        )

    def test_extension_is_preserved_in_default_output_name(self):
        for original, expected in (
            ("holiday.mov", "holiday-mov_pillarboxed.mp4"),
            ("holiday.mp4", "holiday-mp4_pillarboxed.mp4"),
            ("family.trip.mov", "family.trip-mov_pillarboxed.mp4"),
            ("no_extension", "no_extension_pillarboxed.mp4"),
        ):
            with self.subTest(original=original):
                self.assertEqual(conversion.output_path_for(self.root / original), self.root / expected)

    def test_video_info_reads_geometry_and_duration_with_one_probe(self):
        source = self.make_source()
        with patch.object(conversion.subprocess, "Popen", wraps=subprocess.Popen) as probe:
            info = conversion.read_video_info(self.ffmpeg, source, hide_console=True)
        self.assertEqual((info.width, info.height), (180, 320))
        self.assertAlmostEqual(info.duration, 1.0, delta=0.05)
        self.assertEqual(probe.call_count, 1)

    def test_video_info_keeps_unknown_or_zero_duration_as_none(self):
        for duration in ("N/A", "00:00:00.00", None):
            with self.subTest(duration=duration):
                duration_line = f"  Duration: {duration}, start: 0.000000\n" if duration else ""
                diagnostics = (
                    duration_line
                    + "[Parsed_showinfo_0] n: 0 pts: 0 sar:1/1 s:18x32\n"
                    + "frame=1 time=00:00:01.00\n"
                ).encode()
                with patch.object(conversion.subprocess, "Popen") as probe:
                    process = probe.return_value.__enter__.return_value
                    process.communicate.return_value = (None, diagnostics)
                    process.returncode = 0
                    info = conversion.read_video_info("ffmpeg", self.root / "unknown.mp4")
                self.assertEqual((info.width, info.height), (18, 32))
                self.assertIsNone(info.duration)

    def test_gui_callbacks_capture_diagnostics_and_progress(self):
        source = self.make_source()
        original = source.read_bytes()
        messages, progress = [], []
        output_text, error_text = io.StringIO(), io.StringIO()
        with redirect_stdout(output_text), redirect_stderr(error_text):
            output = conversion.convert(
                self.args(source), log=messages.append, progress=progress.append,
                source_dimensions=(180, 320), hide_console=True,
            )
        self.assertEqual(output.name, "holiday-mp4_pillarboxed.mp4")
        self.assertTrue(output.is_file())
        self.assertEqual(output_text.getvalue(), "")
        self.assertEqual(error_text.getvalue(), "")
        self.assertTrue(any("libx264" in line for line in messages))
        self.assertTrue(progress)
        self.assertGreater(max(progress), 0)
        self.assertEqual(source.read_bytes(), original)

    def test_cancelling_a_running_conversion_cleans_temporary_output(self):
        source = self.make_source()
        stop = threading.Event()

        def on_progress(seconds):
            stop.set()

        with self.assertRaises(conversion.ConversionCancelled):
            conversion.convert(
                self.args(source), log=lambda line: None, progress=on_progress,
                cancel_event=stop, hide_console=True,
            )
        self.assertTrue(stop.is_set())
        self.assertTrue(source.is_file())
        self.assertFalse(conversion.output_path_for(source).exists())
        self.assertFalse(list(self.root.glob(".*.mp4")))

    def test_cancelled_probe_does_not_launch_child(self):
        stop = threading.Event()
        stop.set()
        # The invalid executable would raise OSError if a child were launched.
        with self.assertRaises(conversion.ConversionCancelled):
            conversion.read_dimensions("missing-ffmpeg", self.root / "missing.mp4", cancel_event=stop)

    def test_probe_timeout_is_reported(self):
        source = self.make_source()
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            conversion.read_dimensions(self.ffmpeg, source, hide_console=True, timeout=0)


if __name__ == "__main__":
    unittest.main()
