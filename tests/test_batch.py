"""Batch integration checks using synthetic videos in isolated temp folders."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import imageio_ffmpeg

from video_landscaper import batch


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="video-landscaper-batch-test-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def video(self, name="portrait.mp4", size=(18, 32)):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-f", "lavfi", "-i", f"testsrc2=s={size[0]}x{size[1]}:r=10",
             "-t", "0.3", "-c:v", "libx264", "-preset", "ultrafast",
             "-f", "mp4", str(path)],
            check=True, capture_output=True,
        )
        return path

    def scan(self):
        return batch.scan_folder(self.folder, on_log=lambda message: None)

    def run_items(self, rows, **kwargs):
        return batch.run_batch(rows, on_log=lambda message: None, **kwargs)

    def pending_rename(self):
        source = self.video()
        rows = self.scan()
        with patch.object(batch, "rename_original", side_effect=PermissionError("source is open")):
            result = self.run_items(rows)
        self.assertEqual(result.failed, 1)
        self.assertEqual(rows[0].status, "rename_pending")
        self.assertTrue(source.exists())
        self.assertTrue(rows[0].output.exists())
        return source, rows[0].output

    def test_scan_selection_exclusions_and_no_recursion(self):
        portrait = self.video()
        self.video("landscape.mp4", (32, 18))
        self.video("square.mp4", (20, 20))
        self.video("subfolder/nested.mp4")
        shutil.copyfile(portrait, self.folder / "backup.mp4.original")
        shutil.copyfile(portrait, self.folder / "old-mp4_pillarboxed.mp4")
        (self.folder / "notes.txt").write_text("ordinary text, not a video", encoding="utf-8")
        rows = {row.source.name: row for row in self.scan()}
        self.assertEqual(set(rows), {"portrait.mp4", "landscape.mp4", "square.mp4"})
        row = rows["portrait.mp4"]
        self.assertEqual((row.width, row.height), (18, 32))
        self.assertEqual(row.status, "ready")
        self.assertTrue(row.selected)
        self.assertTrue(row.selectable)
        for name in ("landscape.mp4", "square.mp4"):
            self.assertEqual(rows[name].status, "ineligible")
            self.assertFalse(rows[name].selected)
            self.assertFalse(rows[name].selectable)
        for row in rows.values():
            self.assertAlmostEqual(row.duration, 0.3, delta=0.05)

    def test_unknown_duration_does_not_prevent_video_selection(self):
        source = self.folder / "unknown-duration.mp4"
        source.write_bytes(b"mock video")
        with patch.object(batch.conversion, "read_video_info", return_value=batch.conversion.VideoInfo(18, 32, None)):
            rows = self.scan()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].duration)
        self.assertEqual(rows[0].status, "ready")
        self.assertTrue(rows[0].selected)

    def test_same_stem_different_extensions_succeed_independently(self):
        first = self.video("holiday.mov")
        second = self.video("holiday.mp4")
        original_data = {path.name: path.read_bytes() for path in (first, second)}
        rows = self.scan()
        self.assertEqual({row.output.name for row in rows},
                         {"holiday-mov_pillarboxed.mp4", "holiday-mp4_pillarboxed.mp4"})
        result = self.run_items(rows)
        self.assertEqual((result.completed, result.failed), (2, 0))
        for row in rows:
            self.assertEqual(row.status, "done")
            self.assertFalse(row.selected)
            self.assertFalse(row.selectable)
            self.assertTrue(row.output.is_file())
            self.assertFalse(row.source.exists())
            self.assertEqual(row.source.with_name(row.source.name + ".original").read_bytes(),
                             original_data[row.source.name])

    def test_scan_uses_display_rotation_for_portrait_selection(self):
        stored = self.video("stored.mp4", size=(32, 18))
        rotated = self.folder / "rotated.mp4"
        subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-display_rotation:v:0", "90", "-i", str(stored), "-c", "copy", str(rotated)],
            check=True, capture_output=True,
        )
        stored.unlink()
        rows = self.scan()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].width, rows[0].height), (18, 32))
        self.assertEqual(rows[0].status, "ready")
        self.assertTrue(rows[0].selected)

    def test_existing_output_is_a_blocking_conflict(self):
        source = self.video()
        output = self.folder / "portrait-mp4_pillarboxed.mp4"
        output.write_bytes(b"preserve existing output")
        rows = self.scan()
        self.assertEqual(rows[0].status, "conflict")
        self.assertFalse(rows[0].selectable)
        self.run_items(rows)
        self.assertTrue(source.exists())
        self.assertEqual(output.read_bytes(), b"preserve existing output")

    def test_existing_original_backup_is_a_blocking_conflict(self):
        source = self.video()
        backup = source.with_name(source.name + ".original")
        backup.write_bytes(b"preserve existing original")
        rows = self.scan()
        self.assertEqual(rows[0].status, "conflict")
        self.assertFalse(rows[0].selectable)
        self.run_items(rows)
        self.assertTrue(source.exists())
        self.assertEqual(backup.read_bytes(), b"preserve existing original")
        self.assertFalse(rows[0].output.exists())

    def test_extensionless_name_collision_is_detected(self):
        self.video("same.mp4")
        self.video("same-mp4")
        rows = self.scan()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.status, "conflict")
            self.assertFalse(row.selected)
            self.assertFalse(row.selectable)

    def test_conversion_failure_stops_remaining_files(self):
        self.video("a.mp4")
        self.video("b.mp4")
        rows = self.scan()
        with patch.object(batch.conversion, "convert", side_effect=RuntimeError("encoder failed")) as convert:
            result = self.run_items(rows)
        self.assertEqual((result.completed, result.failed), (0, 1))
        self.assertEqual(convert.call_count, 1)
        self.assertEqual(rows[0].status, "failed")
        self.assertEqual(rows[1].status, "not_processed")
        self.assertTrue(all(row.source.exists() for row in rows))
        self.assertFalse(any(row.output.exists() for row in rows))

    def test_stop_after_current_finishes_and_renames_active_file(self):
        self.video("a.mp4")
        self.video("b.mp4")
        rows = self.scan()
        stop = threading.Event()

        def changed(row):
            if row.status == "done":
                stop.set()

        result = self.run_items(rows, on_item=changed, stop_event=stop)
        self.assertEqual((result.completed, result.failed), (1, 0))
        self.assertTrue(result.stopped)
        self.assertEqual(rows[0].status, "done")
        self.assertEqual(rows[1].status, "not_processed")
        self.assertFalse(rows[0].source.exists())
        self.assertTrue(rows[0].source.with_name(rows[0].source.name + ".original").exists())
        self.assertTrue(rows[1].source.exists())
        self.assertFalse(rows[1].output.exists())

    def test_rename_failure_can_resume_without_reencoding(self):
        source, output = self.pending_rename()
        output_data = output.read_bytes()
        rows = self.scan()
        self.assertEqual(rows[0].status, "rename_pending")
        self.assertTrue(rows[0].selectable)
        self.assertTrue(rows[0].selected)
        with patch.object(batch.conversion, "convert", side_effect=AssertionError("must not re-encode")):
            result = self.run_items(rows)
        self.assertEqual((result.completed, result.failed), (1, 0))
        self.assertEqual(rows[0].status, "done")
        self.assertFalse(source.exists())
        self.assertTrue(source.with_name(source.name + ".original").exists())
        self.assertEqual(output.read_bytes(), output_data)

    def test_no_history_write_occurs_after_original_is_renamed(self):
        source = self.video()
        rows = self.scan()
        write_history = batch._write_history
        backup = source.with_name(source.name + ".original")

        def guarded_write(folder, history):
            if backup.exists():
                raise PermissionError("history became unavailable after rename")
            write_history(folder, history)

        with patch.object(batch, "_write_history", side_effect=guarded_write) as write:
            result = self.run_items(rows)
        self.assertEqual((result.completed, result.failed), (1, 0))
        self.assertEqual(write.call_count, 2)
        self.assertEqual(rows[0].status, "done")
        self.assertFalse(rows[0].selected)
        self.assertFalse(rows[0].selectable)
        self.assertFalse(source.exists())
        self.assertTrue(backup.exists())
        self.assertTrue(rows[0].output.exists())

    def test_deleted_output_after_rename_failure_can_be_reconverted(self):
        source, output = self.pending_rename()
        output.unlink()
        rows = self.scan()
        self.assertEqual(rows[0].status, "ready")
        self.assertTrue(rows[0].selected)
        convert = batch.conversion.convert
        with patch.object(batch.conversion, "convert", wraps=convert) as conversion:
            result = self.run_items(rows)
        self.assertEqual((result.completed, result.failed), (1, 0))
        self.assertEqual(conversion.call_count, 1)
        self.assertEqual(rows[0].status, "done")
        self.assertFalse(source.exists())
        self.assertTrue(source.with_name(source.name + ".original").exists())
        self.assertTrue(output.exists())

    def test_modified_output_blocks_rename_recovery(self):
        source, output = self.pending_rename()
        output.write_bytes(output.read_bytes() + b"changed output")
        rows = self.scan()
        self.assertEqual(rows[0].status, "conflict")
        self.assertFalse(rows[0].selectable)
        self.run_items(rows)
        self.assertTrue(source.exists())
        self.assertFalse(source.with_name(source.name + ".original").exists())

    def test_modified_source_blocks_rename_recovery(self):
        source, output = self.pending_rename()
        source.write_bytes(source.read_bytes() + b"changed source")
        rows = self.scan()
        self.assertEqual(rows[0].status, "conflict")
        self.assertFalse(rows[0].selectable)
        self.run_items(rows)
        self.assertTrue(source.exists())
        self.assertFalse(source.with_name(source.name + ".original").exists())

    def test_changed_source_after_scan_fails_preflight(self):
        source = self.video()
        rows = self.scan()
        source.write_bytes(source.read_bytes() + b"changed after scan")
        with patch.object(batch.conversion, "convert", side_effect=AssertionError("must not convert")):
            result = self.run_items(rows)
        self.assertEqual(result.failed, 1)
        self.assertTrue(source.exists())
        self.assertFalse(rows[0].output.exists())

    def test_output_appearing_after_scan_is_preserved(self):
        source = self.video()
        rows = self.scan()
        rows[0].output.write_bytes(b"appeared after scan")
        with patch.object(batch.conversion, "convert", side_effect=AssertionError("must not convert")):
            result = self.run_items(rows)
        self.assertEqual(result.failed, 1)
        self.assertTrue(source.exists())
        self.assertEqual(rows[0].output.read_bytes(), b"appeared after scan")

    def test_output_verification_failure_leaves_source_untouched(self):
        source = self.video()
        rows = self.scan()
        with patch.object(batch, "_verify_output", side_effect=RuntimeError("output failed verification")):
            result = self.run_items(rows)
        self.assertEqual(result.failed, 1)
        self.assertEqual(rows[0].status, "failed")
        self.assertTrue(source.exists())
        self.assertFalse(source.with_name(source.name + ".original").exists())
        self.assertTrue(rows[0].output.exists())
        rescanned = self.scan()
        self.assertEqual(rescanned[0].status, "conflict")
        self.assertFalse(rescanned[0].selectable)

    def test_concurrent_batch_lock_prevents_modifications(self):
        source = self.video()
        rows = self.scan()
        with batch._batch_lock(self.folder):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                self.run_items(rows)
        self.assertTrue(source.exists())
        self.assertFalse(rows[0].output.exists())
        self.assertFalse(source.with_name(source.name + ".original").exists())

    def test_unreadable_history_is_not_silently_replaced(self):
        source = self.video()
        history = self.folder / ".pillarbox-batch.json"
        history.write_bytes(b"malformed history; preserve this file")
        with self.assertRaises(ValueError):
            self.scan()
        self.assertEqual(history.read_bytes(), b"malformed history; preserve this file")
        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
