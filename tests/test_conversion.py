"""Small end-to-end tests using only the bundled FFmpeg and temporary media."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import imageio_ffmpeg

from video_landscaper import cli, conversion


class Test01_LayoutTests(unittest.TestCase):
    def test_requested_defaults(self):
        args = cli.make_parser().parse_args(["input.mp4"])
        self.assertEqual(vars(args), vars(conversion.ConversionOptions(input=Path("input.mp4"))))
        self.assertEqual((args.max_width, args.max_height), (1920, 1080))
        self.assertEqual((args.blur, args.preset), (90, "slow"))

    def test_layout_examples_and_maximum_bounds(self):
        cases = [
            # Input, limits, expected foreground, expected canvas.
            ((160, 90), (1920, 1080), (160, 90), (160, 90)),
            ((90, 160), (1920, 1080), (90, 160), (284, 160)),
            ((100, 100), (1920, 1080), (100, 100), (176, 100)),
            ((320, 90), (1920, 1080), (320, 90), (320, 180)),
            ((1920, 1080), (1920, 1080), (1920, 1080), (1920, 1080)),
            ((3840, 2160), (1920, 1080), (1920, 1080), (1920, 1080)),
            ((720, 1280), (1920, 1080), (607, 1080), (1920, 1080)),
            ((2560, 720), (1920, 1080), (1920, 540), (1920, 1080)),
            ((160, 90), (1080, 1920), (160, 90), (160, 284)),
            ((91, 161), (1920, 1080), (91, 161), (288, 162)),
        ]
        for source, limits, foreground, canvas in cases:
            with self.subTest(source=source, limits=limits):
                layout = conversion.calculate_layout(*source, *limits)
                self.assertEqual((layout.foreground_width, layout.foreground_height), foreground)
                self.assertEqual((layout.output_width, layout.output_height), canvas)

    def test_layout_invariants_for_varied_shapes(self):
        for limits in ((1920, 1080), (1080, 1920), (100, 100), (2, 6)):
            for width in (1, 2, 89, 90, 161, 1919, 4000):
                for height in (1, 2, 89, 90, 161, 1079, 3000):
                    with self.subTest(source=(width, height), limits=limits):
                        layout = conversion.calculate_layout(width, height, *limits)
                        self.assertLessEqual(layout.foreground_width, width)
                        self.assertLessEqual(layout.foreground_height, height)
                        self.assertLessEqual(layout.foreground_width, layout.output_width)
                        self.assertLessEqual(layout.foreground_height, layout.output_height)
                        self.assertLessEqual(layout.output_width, limits[0])
                        self.assertLessEqual(layout.output_height, limits[1])
                        self.assertEqual(layout.output_width % 2, 0)
                        self.assertEqual(layout.output_height % 2, 0)
                        if width <= limits[0] and height <= limits[1]:
                            self.assertEqual((layout.foreground_width, layout.foreground_height), (width, height))


class Test02_ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="video-landscaper-test-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def ffmpeg_run(self, *arguments):
        return subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
            check=True, capture_output=True,
        )

    def make_source(self, audio=False, sar=1, size=(180, 320)):
        source = self.root / "source with spaces.mp4"
        pattern = (
            f"color=c=red:s={size[0]}x{size[1]}:r=10,format=yuv444p,"
            "drawbox=x=0:y=0:w=iw/3:h=ih:color=lime:t=fill,"
            "drawbox=x=2*iw/3:y=0:w=iw/3:h=ih:color=blue:t=fill,"
            f"setsar={sar}"
        )
        arguments = ["-y", "-f", "lavfi", "-i", pattern]
        if audio:
            arguments += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
        arguments += ["-t", "0.6", "-c:v", "libx264", "-preset", "ultrafast"]
        if audio:
            arguments += ["-c:a", "aac", "-b:a", "64k"]
        self.ffmpeg_run(*arguments, str(source))
        return source

    def convert(self, source, *extra):
        args = cli.make_parser().parse_args([
            str(source), "--max-width", "320", "--max-height", "180",
            "--preset", "ultrafast", *extra,
        ])
        with redirect_stdout(io.StringIO()):
            return conversion.convert(conversion.ConversionOptions(**vars(args)))

    def read_frame(self, output, size=(320, 180)):
        reader = imageio_ffmpeg.read_frames(str(output), pix_fmt="rgb24")
        try:
            metadata = next(reader)
            frame = next(reader)
        finally:
            reader.close()
        self.assertEqual(metadata["size"], size)
        self.assertEqual(len(frame), size[0] * size[1] * 3)
        return metadata, frame

    def assert_color(self, frame, x, channel):
        offset = (90 * 320 + x) * 3
        pixel = frame[offset:offset + 3]
        self.assertGreater(pixel[channel], 180, pixel)
        self.assertLess(max(pixel[i] for i in range(3) if i != channel), 75, pixel)

    def test_portrait_with_audio_and_duration(self):
        source = self.make_source(audio=True)
        original = source.read_bytes()
        output = self.convert(source, "--duration", "0.3")
        metadata, frame = self.read_frame(output)
        self.assertIn("h264", metadata["codec"])
        self.assertLessEqual(metadata["duration"], 0.4)
        self.assert_color(frame, 120, 1)  # Whole left edge of foreground fits.
        self.assert_color(frame, 160, 0)
        self.assert_color(frame, 200, 2)  # Whole right edge fits too.
        inspection = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-i", str(output), "-f", "null", "-"],
            capture_output=True, check=True,
        ).stderr.decode(errors="replace")
        self.assertIn("Audio: aac", inspection)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".*.mp4")))

    def test_silent_anamorphic_source(self):
        source = self.make_source(sar=2)
        output = self.convert(source)
        metadata, frame = self.read_frame(output)
        audio_check = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-i", str(output),
             "-map", "0:a:0", "-f", "null", "-"],
            capture_output=True,
        )
        self.assertNotEqual(audio_check.returncode, 0)
        self.assertIn(b"matches no streams", audio_check.stderr)
        # A 2:1 pixel aspect ratio makes the foreground twice as wide.
        self.assert_color(frame, 80, 1)
        self.assert_color(frame, 160, 0)
        self.assert_color(frame, 240, 2)

    def audio_data(self, path):
        return self.ffmpeg_run(
            "-i", str(path), "-map", "0:a:0", "-c:a", "copy",
            "-f", "adts", "pipe:1",
        ).stdout

    def test_default_audio_preserves_compressed_data(self):
        source = self.make_source(audio=True)
        original_audio = self.audio_data(source)
        output = self.convert(source)
        self.assertTrue(original_audio)
        self.assertEqual(self.audio_data(output), original_audio)

    def test_explicit_audio_bitrate_reencodes_to_aac(self):
        source = self.make_source(audio=True)
        output = self.convert(source, "--audio-bitrate", "32k")
        encoded_audio = self.audio_data(output)
        self.assertTrue(encoded_audio)
        self.assertNotEqual(encoded_audio, self.audio_data(source))
        # Include ADTS headers in this loose rate ceiling to allow AAC's
        # short-clip overhead and normal deviation from the requested target.
        self.assertLess(len(encoded_audio) * 8 / 0.6, 60000)

    def test_phone_rotation_and_default_limits_cli(self):
        source = self.make_source()
        rotated = self.root / "rotated.mp4"
        self.ffmpeg_run(
            "-display_rotation:v:0", "90", "-i", str(source), "-c", "copy",
            str(rotated),
        )
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "video-landscaper-single.py"),
             str(rotated), "--duration", "0.2"],
            capture_output=True, check=True,
        )
        self.assertIn(b"Saved:", result.stdout)
        output = conversion.output_path_for(rotated)
        reader = imageio_ffmpeg.read_frames(str(output), pix_fmt="rgb24")
        try:
            metadata = next(reader)
            frame = next(reader)
        finally:
            reader.close()
        self.assertEqual(metadata["size"], (320, 180))
        # Rotation makes the vertical stripes horizontal. Red should extend
        # across the center row rather than being confined to a narrow column.
        for x in (80, 160, 240):
            offset = (90 * 320 + x) * 3
            self.assertGreater(frame[offset], 180, (x, frame[offset:offset + 3]))
            self.assertLess(frame[offset + 1], 75)
            self.assertLess(frame[offset + 2], 75)

    def test_small_inputs_and_alternate_ratios(self):
        cases = [
            ((160, 90), (1920, 1080), (160, 90)),
            ((90, 160), (1920, 1080), (284, 160)),
            ((91, 161), (1920, 1080), (288, 162)),
            ((100, 100), (1920, 1080), (176, 100)),
            ((320, 90), (1920, 1080), (320, 180)),
            ((160, 90), (1080, 1920), (160, 284)),
        ]
        for source_size, limits, output_size in cases:
            with self.subTest(source=source_size, limits=limits):
                source = self.make_source(size=source_size)
                self.assertEqual(conversion.read_dimensions(self.ffmpeg, source), source_size)
                output = self.convert(
                    source, "--max-width", str(limits[0]),
                    "--max-height", str(limits[1]), "--overwrite",
                )
                _, frame = self.read_frame(output, size=output_size)
                # The same source pixels remain at the same offsets within
                # the centered sharp picture; only surrounding bars change.
                origin_x = ((output_size[0] - source_size[0]) // 2) // 2 * 2
                origin_y = ((output_size[1] - source_size[1]) // 2) // 2 * 2
                for fraction, channel in ((1/6, 1), (1/2, 0), (5/6, 2)):
                    x = origin_x + int(source_size[0] * fraction)
                    y = origin_y + source_size[1] // 2
                    offset = (y * output_size[0] + x) * 3
                    self.assertGreater(frame[offset + channel], 180)
                    self.assertLess(max(frame[offset + i] for i in range(3) if i != channel), 75)

    def test_oversized_inputs_shrink_to_bounds(self):
        for source_size in ((640, 360), (200, 400), (640, 160)):
            with self.subTest(source=source_size):
                source = self.make_source(size=source_size)
                output = self.convert(source, "--overwrite")
                self.read_frame(output, size=(320, 180))

    def test_overwrite_and_same_file_protection(self):
        source = self.make_source()
        output = self.root / "existing.mp4"
        output.write_bytes(b"keep existing output")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.convert(source, "-o", str(output))
        self.assertEqual(output.read_bytes(), b"keep existing output")
        with self.assertRaisesRegex(ValueError, "different files"):
            self.convert(source, "-o", str(source), "--overwrite")
        self.convert(source, "-o", str(output), "--overwrite")
        self.read_frame(output)

    def test_failed_conversion_removes_temporary_output(self):
        source = self.root / "invalid.mp4"
        source.write_bytes(b"not a video")
        output = self.root / "existing.mp4"
        output.write_bytes(b"keep existing output")
        with self.assertRaisesRegex(RuntimeError, "FFmpeg failed"):
            self.convert(source, "-o", str(output), "--overwrite")
        self.assertEqual(output.read_bytes(), b"keep existing output")
        self.assertFalse(list(self.root.glob(".*.mp4")))


if __name__ == "__main__":
    unittest.main()
