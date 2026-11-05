"""Exercise GUI state and worker callbacks without processing real videos."""

from dataclasses import replace
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from video_landscaper import gui as batch_gui
from video_landscaper.batch import BatchItem, BatchResult


class BatchGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.destroy_root)
        self.app = batch_gui.BatchApp(self.root, auto_scan=False)
        self.folder = Path(tempfile.gettempdir()) / "video-landscaper-gui-test"
        self.portrait = BatchItem(self.folder / "portrait.mp4", 90, 160)
        self.landscape = BatchItem(self.folder / "landscape.mp4", 160, 90, status="ineligible", selected=False)

    def destroy_root(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def wait_finished(self):
        deadline = time.monotonic() + 3
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertIsNone(self.app.busy)

    def add_items(self):
        self.app._show_item(replace(self.portrait))
        self.app._show_item(replace(self.landscape))

    def test_scan_callbacks_fill_selectable_portrait_rows(self):
        def fake_scan(folder, *, on_item, on_log, stop_event):
            on_log("Scanning synthetic items")
            on_item(self.portrait)
            on_item(self.landscape)
            return [self.portrait, self.landscape]

        with patch.object(batch_gui.engine, "scan_folder", fake_scan):
            self.app.start_scan(self.folder)
            self.wait_finished()
        self.assertEqual(len(self.app.items), 2)
        self.assertTrue(self.app.items[str(self.portrait.source)].selected)
        self.assertFalse(self.app.tree.item(self.app.row_ids[str(self.landscape.source)], "image"))

    def test_selection_controls_and_space_leave_landscape_unselected(self):
        self.add_items()
        self.app.set_selection(False)
        self.assertFalse(self.app.items[str(self.portrait.source)].selected)
        self.app.set_selection(True)
        self.assertTrue(self.app.items[str(self.portrait.source)].selected)
        self.assertFalse(self.app.items[str(self.landscape.source)].selected)
        self.app.tree.focus(self.app.row_ids[str(self.portrait.source)])
        self.app._space_checkbox(None)
        self.assertFalse(self.app.items[str(self.portrait.source)].selected)

    def test_batch_worker_updates_status_log_and_removes_completed_checkbox(self):
        self.add_items()

        def fake_run(items, *, on_item, on_log, on_progress, stop_event):
            item = next(item for item in items if item.selected)
            item.status = "converting"
            item.detail = "Converting"
            on_item(item)
            on_progress(item, 1.5)
            item.status = "done"
            item.selected = False
            item.detail = "Original renamed"
            on_item(item)
            on_log("Synthetic conversion complete")
            return BatchResult(1, 0, False, "Completed 1 video")

        with patch.object(batch_gui.engine, "run_batch", fake_run):
            self.app.start_batch()
            self.wait_finished()
        item = self.app.items[str(self.portrait.source)]
        self.assertEqual(item.status, "done")
        self.assertEqual(self.app.status_text.get(), "Completed 1 video")
        row = self.app.row_ids[str(item.source)]
        self.assertFalse(self.app.tree.item(row, "image"))
        self.assertEqual(self.app.tree.item(row, "tags"), ("green",))
        self.assertIn("Synthetic conversion complete", "".join(self.app.log_lines))

    def test_status_has_no_duplicate_detail_and_selected_detail_updates(self):
        self.add_items()
        key = str(self.portrait.source)
        row = self.app.row_ids[key]
        # Check duplicate suppression without tying the test to label wording.
        ready_label = batch_gui.STATUS_TEXT["ready"]
        self.app._show_item(replace(self.portrait, detail=ready_label))
        self.assertEqual(self.app.tree.item(row, "values")[-1], ready_label)
        self.app.tree.selection_set(row)
        changed = replace(self.portrait, status="failed", detail="The disk is full", selected=False)
        self.app._show_item(changed)
        self.assertIn("The disk is full", self.app.detail_text.get())
        self.assertEqual(self.app.tree.item(row, "tags"), ("red",))

    def test_duration_column_follows_height_and_formats_minutes_without_padding(self):
        self.assertEqual(self.app.tree["columns"], ("filename", "width", "height", "duration", "status"))
        self.assertEqual(self.app.tree.heading("duration", "text"), "Duration")
        for duration, expected in ((5.9, "0:05"), (72, "1:12"), (3912, "65:12"), (None, "—")):
            with self.subTest(duration=duration):
                item = replace(self.portrait, duration=duration)
                self.app._show_item(item)
                row = self.app.row_ids[str(item.source)]
                self.assertEqual(self.app.tree.set(row, "duration"), expected)

    def test_progress_tick_updates_only_the_converting_status_without_changing_details(self):
        self.app.busy = "run"
        self.app.started_at = 100
        self.app.run_total = 4
        item = replace(self.portrait, duration=100, status="converting", detail="Converting")
        self.app._show_item(item)
        row = self.app.row_ids[str(item.source)]
        self.app.tree.selection_set(row)
        self.app._show_detail()
        details = self.app.detail_text.get()
        self.app._queue_progress(item, 25.37)
        self.app._drain_events()
        with patch.object(batch_gui.time, "monotonic", return_value=108):
            self.app._tick()
            self.app._tick()
        self.assertEqual(self.app.tree.set(row, "status"), f"{batch_gui.STATUS_TEXT['converting']} — Converted 25%")
        self.assertEqual(item.detail, "Converting")
        self.assertEqual(self.app.detail_text.get(), details)
        self.assertEqual(self.app.tree.item(row, "tags"), ("blue",))
        self.assertEqual(self.app.progress_text.get(), "0 of 4 video(s) completed • Time elapsed: 0:08")

    def test_batch_elapsed_spans_videos_and_new_batch_clears_previous_progress(self):
        first = replace(self.portrait, duration=100)
        second = replace(first, source=self.folder / "second.mp4")
        self.app._show_item(first)
        self.app._show_item(second)
        self.app.progress_text.set("Old progress")
        self.app.video_seconds = 99
        with patch.object(batch_gui.threading, "Thread"), patch.object(batch_gui.time, "monotonic", return_value=100):
            self.app.start_batch()
        self.assertEqual(self.app.progress_text.get(), "0 of 2 video(s) completed • Time elapsed: 0:00")
        self.assertEqual(self.app.video_seconds, 0)
        self.app._show_item(replace(first, status="converting", detail="Converting"))
        self.app.video_seconds = 45
        self.app._show_item(replace(first, status="done", detail="Original renamed", selected=False))
        with patch.object(batch_gui.time, "monotonic", return_value=112):
            self.app._show_item(replace(second, status="converting", detail="Converting"))
            self.app._tick()
        self.assertEqual(self.app.started_at, 100)
        self.assertEqual(self.app.video_seconds, 0)
        self.assertEqual(self.app.progress_text.get(), "1 of 2 video(s) completed • Time elapsed: 0:12")
        second_row = self.app.row_ids[str(second.source)]
        self.assertTrue(self.app.tree.set(second_row, "status").endswith("Converted 0%"))

    def test_unknown_duration_shows_converted_time_and_percentage_stays_within_bounds(self):
        self.app.busy = "run"
        for duration, seconds, expected in (
            (None, 70, "Converted 1:10 of video"),
            (0, 70, "Converted 1:10 of video"),
            (20, -5, "Converted 0%"),
            (20, 19.999, "Converted 99%"),
            (20, 25, "Converted 100%"),
        ):
            with self.subTest(duration=duration, seconds=seconds):
                item = replace(self.portrait, duration=duration, status="converting", detail="Converting")
                self.app._show_item(item)
                self.app.video_seconds = seconds
                self.app._tick()
                row = self.app.row_ids[str(item.source)]
                self.assertEqual(self.app.tree.set(row, "status"), f"{batch_gui.STATUS_TEXT['converting']} — {expected}")

    def test_late_progress_and_ticks_do_not_overwrite_finished_or_failed_rows(self):
        self.app.busy = "run"
        for status, tag in (("done", "green"), ("failed", "red")):
            with self.subTest(status=status):
                item = replace(self.portrait, duration=100, status="converting", detail="Converting")
                self.app._show_item(item)
                self.app._show_item(replace(item, status=status, selected=False, detail="Final detail"))
                row = self.app.row_ids[str(item.source)]
                final_values = self.app.tree.item(row, "values")
                self.app._queue_progress(item, 99)
                self.app._drain_events()
                self.app._tick()
                self.assertEqual(self.app.tree.item(row, "values"), final_values)
                self.assertEqual(self.app.tree.item(row, "tags"), (tag,))

    def test_stop_request_waits_for_current_instead_of_killing_worker(self):
        self.add_items()
        self.app.busy = "run"
        self.app.stop_after_current()
        self.assertTrue(self.app.stop_event.is_set())
        self.assertEqual(self.app.busy, "run")
        self.assertIn("active conversion and original rename will finish", "".join(self.app.log_lines))


if __name__ == "__main__":
    unittest.main()
