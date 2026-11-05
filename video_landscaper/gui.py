"""Video Landscaper's Windows batch interface and queued worker updates."""

import argparse
from dataclasses import replace
from datetime import datetime
import math
from pathlib import Path
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import batch as engine
from . import conversion


STATUS_TEXT = {
    "ready": "Portrait video",
    "ineligible": "Landscape video",
    "conflict": "Filename conflict",
    "rename_pending": "Converted",
    "done": "✔️ Done",
    "failed": "❌ Failed",
    "not_processed": "Not processed",
    "converting": "⏳ Conversion in progress",
    "verifying": "⏳ Checking output",
    "renaming": "⏳ Renaming original",
}


def elapsed_text(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def duration_text(seconds):
    """Show a video's duration as minutes:seconds, including durations over an hour."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "—"
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02}"


class BatchApp:
    def __init__(self, root, initial_folder=None, *, auto_scan=True):
        self.root = root
        self.folder = None
        self.items = {}
        self.row_ids = {}
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = None
        self.closing = False
        self.worker = None
        self.started_at = None
        self.video_seconds = 0
        self.active_key = ""
        self.run_total = 0
        self.run_done = set()
        self.log_lines = []
        self.log_visible = False
        self.pending_after = set()

        root.title("Video Landscaper")
        root.geometry("1100x740")
        root.minsize(900, 560)
        root.option_add("*Font", "{Segoe UI} 10")
        root.protocol("WM_DELETE_WINDOW", self.request_close)
        root.bind("<Destroy>", self._root_destroyed, add=True)
        root.report_callback_exception = self.report_callback_exception
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Go.TButton", font=("Segoe UI", 12, "bold"), padding=(10, 5))

        self.checked_image = self._checkbox_image(True)
        self.unchecked_image = self._checkbox_image(False)
        self._build_widgets()
        self._schedule(70, self._drain_events)
        self._schedule(500, self._tick)
        if auto_scan:
            if initial_folder is None:
                self._schedule(150, self.choose_folder)
            else:
                self._schedule(100, lambda: self.start_scan(Path(initial_folder)))

    def _schedule(self, delay, callback):
        def invoke():
            self.pending_after.discard(after_id)
            callback()
        after_id = self.root.after(delay, invoke)
        self.pending_after.add(after_id)

    def _root_destroyed(self, event):
        if event.widget is not self.root:
            return
        for after_id in self.pending_after:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self.pending_after.clear()

    def _checkbox_image(self, checked):
        image = tk.PhotoImage(master=self.root, width=18, height=18)
        image.put("#ffffff", to=(2, 2, 16, 16))
        outline = "#245dad" if checked else "#747b85"
        for rectangle in ((2, 2, 16, 3), (2, 15, 16, 16), (2, 2, 3, 16), (15, 2, 16, 16)):
            image.put(outline, to=rectangle)
        if checked:
            for x, y in ((5, 8), (6, 9), (7, 10), (8, 11), (9, 10), (10, 9), (11, 8), (12, 7), (13, 6)):
                image.put("#245dad", to=(x, y, x + 2, y + 2))
        return image

    def _build_widgets(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        folder_bar = ttk.Frame(outer)
        folder_bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        folder_bar.columnconfigure(0, weight=1)
        self.folder_text = tk.StringVar(value="") # or value="Choose the location of your videos"
        ttk.Label(folder_bar, textvariable=self.folder_text).grid(row=0, column=0, sticky="w")
        self.choose_button = ttk.Button(folder_bar, text="Choose folder…", command=self.choose_folder)
        self.choose_button.grid(row=0, column=1, padx=(12, 6))
        self.rescan_button = ttk.Button(folder_bar, text="Rescan", command=self.rescan)
        self.rescan_button.grid(row=0, column=2)

        ttk.Label(outer, text="The following videos will be converted from Portrait to Landscape (16:9) with:", style="Header.TLabel").grid(row=1, column=0, sticky="w")
        defaults = conversion.ConversionOptions(input=Path("unused"))
        ttk.Label(
            outer,
            text=f"Max resolution: {defaults.max_width} × {defaults.max_height}  ·  Blur: {defaults.blur}  ·  CRF: {defaults.crf}  ·  {defaults.preset.capitalize()} encoding  ·  Original audio",
        ).grid(row=2, column=0, sticky="w", pady=(5, 12))

        selection_bar = ttk.Frame(outer)
        selection_bar.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        selection_bar.columnconfigure(2, weight=1)
        self.select_button = ttk.Button(selection_bar, text="Select all", command=lambda: self.set_selection(True))
        self.select_button.grid(row=0, column=0)
        self.clear_button = ttk.Button(selection_bar, text="Clear selection", command=lambda: self.set_selection(False))
        self.clear_button.grid(row=0, column=1, padx=(6, 12))
        self.selection_text = tk.StringVar(value="0 videos selected")
        ttk.Label(selection_bar, textvariable=self.selection_text).grid(row=0, column=2, sticky="w")
        #ttk.Label(selection_bar, text="Click a checkbox or press Space to select").grid(row=0, column=3, sticky="e")

        table = ttk.Frame(outer)
        table.grid(row=4, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("filename", "width", "height", "duration", "status"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Select")
        self.tree.column("#0", width=52, minwidth=52, stretch=False, anchor="center")
        for column, label, width, stretch in (
            ("filename", "Filename", 330, True), ("width", "Width", 75, False),
            ("height", "Height", 75, False), ("duration", "Duration", 85, False),
            ("status", "Status", 430, True),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=width if not stretch else 180, stretch=stretch, anchor="center" if column in {"width", "height", "duration"} else "w")
        self.tree.tag_configure("blue", foreground="#174ca6")
        self.tree.tag_configure("gray", foreground="#707070")
        self.tree.tag_configure("green", foreground="#1d7339")
        self.tree.tag_configure("red", foreground="#b42318")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.bind("<Button-1>", self._click_checkbox, add=True)
        self.tree.bind("<space>", self._space_checkbox)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)

        self.detail_text = tk.StringVar(value="Only portrait videos are selectable. Subfolders are not scanned.")
        self.detail_label = ttk.Label(outer, textvariable=self.detail_text, wraplength=1020)
        self.detail_label.grid(row=5, column=0, sticky="ew", pady=(8, 10))
        self.detail_label.bind("<Configure>", lambda event: self.detail_label.configure(wraplength=max(200, event.width)))

        actions = ttk.Frame(outer)
        actions.grid(row=6, column=0, sticky="ew")
        actions.columnconfigure(2, weight=1)
        self.go_button = ttk.Button(actions, text="Go!", style="Go.TButton", command=self.start_batch)
        self.go_button.grid(row=0, column=0)
        self.stop_button = ttk.Button(actions, text="Stop after current video", command=self.stop_after_current)
        self.stop_button.grid(row=0, column=1, padx=(8, 12))
        self.status_text = tk.StringVar(value="Choose a folder to begin.")
        ttk.Label(actions, textvariable=self.status_text).grid(row=0, column=2, sticky="w")
        self.log_button = ttk.Button(actions, text="Show log", command=self.toggle_log)
        self.log_button.grid(row=0, column=3, padx=(8, 0))

        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=1)
        self.progress.grid(row=7, column=0, sticky="ew", pady=(10, 4))
        self.progress_text = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self.progress_text).grid(row=8, column=0, sticky="w")

        self.log_frame = ttk.Frame(outer)
        self.log_frame.grid(row=9, column=0, sticky="nsew", pady=(10, 0))
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(1, weight=1)
        ttk.Label(self.log_frame, text="Conversion log").grid(row=0, column=0, sticky="w")
        ttk.Button(self.log_frame, text="Save log…", command=self.save_log).grid(row=0, column=1, sticky="e", pady=(0, 5))
        self.log_widget = tk.Text(self.log_frame, height=9, wrap="word", state="disabled", font=("Consolas", 9), background="#f6f7f8", relief="solid", borderwidth=1)
        self.log_widget.grid(row=1, column=0, sticky="nsew", columnspan=2)
        log_scroll = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_widget.yview)
        log_scroll.grid(row=1, column=2, sticky="ns")
        self.log_widget.configure(yscrollcommand=log_scroll.set)
        self.log_frame.grid_remove()
        self._update_controls()

    def choose_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(parent=self.root, title="Choose the location of your videos", initialdir=str(self.folder) if self.folder else None, mustexist=True)
        if folder:
            self.start_scan(Path(folder))
        elif self.folder is None:
            self.root.destroy()

    def rescan(self):
        if self.folder and not self.busy:
            self.start_scan(self.folder)

    def start_scan(self, folder):
        if self.busy:
            return
        self.folder = Path(folder).expanduser().resolve()
        self.folder_text.set(str(self.folder))
        self.items.clear()
        self.row_ids.clear()
        self.tree.delete(*self.tree.get_children())
        self.busy = "scan"
        self.stop_event = threading.Event()
        self.status_text.set("Scanning files in this folder…")
        self.progress_text.set("Subfolders are not scanned.")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self._append_log(f"\nScanning {self.folder}")
        self._update_controls()

        def work():
            try:
                items = engine.scan_folder(self.folder, on_item=self._queue_item, on_log=self._queue_log, stop_event=self.stop_event)
                self.events.put(("scanned", [replace(item) for item in items]))
            except Exception as exc:
                self.events.put(("error", (str(exc), traceback.format_exc())))
        self.worker = threading.Thread(target=work, name="video-landscaper-scan", daemon=True)
        self.worker.start()

    def _queue_item(self, item):
        self.events.put(("item", replace(item)))

    def _queue_log(self, text):
        self.events.put(("log", str(text)))

    def _queue_progress(self, item, seconds):
        self.events.put(("progress", (str(item.source), seconds)))

    def _item_status_text(self, item):
        status = STATUS_TEXT.get(item.status, item.status)
        detail = item.detail.replace("\n", " ").strip()
        if self.busy == "run" and item.status == "converting" and str(item.source) == self.active_key:
            if item.duration is not None and math.isfinite(item.duration) and item.duration > 0:
                percent = max(0, min(100, self.video_seconds / item.duration * 100))
                detail = f"Converted {int(percent)}%"
            else:
                detail = f"Converted {duration_text(max(0, self.video_seconds))} of video"
        if detail and detail.casefold() != status.casefold():
            status += " — " + detail
        return status

    def _show_item(self, item):
        key = str(item.source)
        self.items[key] = item
        if self.busy == "run" and item.status == "converting" and self.active_key != key:
            self.active_key = key
            self.video_seconds = 0
        if item.status == "done":
            tag = "green"
        elif item.status in {"failed", "rename_pending", "conflict"}:
            tag = "red"
        elif item.status == "ineligible":
            tag = "gray"
        else:
            tag = "blue"
        image = (self.checked_image if item.selected else self.unchecked_image) if item.selectable else ""
        values = (item.source.name, item.width or "—", item.height or "—", duration_text(item.duration), self._item_status_text(item))
        if key in self.row_ids:
            self.tree.item(self.row_ids[key], image=image, values=values, tags=(tag,))
        else:
            self.row_ids[key] = self.tree.insert("", "end", image=image, values=values, tags=(tag,))
        if self.row_ids[key] in self.tree.selection():
            self._show_detail()
        if self.busy == "run":
            if item.status in {"converting", "verifying", "renaming"}:
                self.status_text.set(f"{STATUS_TEXT[item.status]}: {item.source.name}")
                self.tree.see(self.row_ids[key])
            elif item.status == "done":
                self.run_done.add(key)
                self.progress.configure(value=len(self.run_done))
        self._update_controls()

    def _item_from_row(self, row):
        return next((self.items[key] for key, row_id in self.row_ids.items() if row_id == row), None)

    def _click_checkbox(self, event):
        row = self.tree.identify_row(event.y)
        if row and self.tree.identify_column(event.x) == "#0":
            self.tree.selection_set(row)
            self.tree.focus(row)
            self._toggle_item(self._item_from_row(row))

    def _space_checkbox(self, event):
        self._toggle_item(self._item_from_row(self.tree.focus()))
        return "break"

    def _toggle_item(self, item):
        if self.busy or item is None or not item.selectable:
            return
        item.selected = not item.selected
        self._show_item(item)

    def set_selection(self, selected):
        if self.busy:
            return
        for item in list(self.items.values()):
            if item.selectable:
                item.selected = selected
                self._show_item(item)

    def _show_detail(self, event=None):
        selected = self.tree.selection()
        item = self._item_from_row(selected[0]) if selected else None
        if item is not None:
            self.detail_text.set(f"Output: {item.output.name}\n{item.detail or STATUS_TEXT.get(item.status, item.status)}")

    def _update_controls(self):
        selectable = [item for item in self.items.values() if item.selectable]
        selected = sum(item.selected for item in selectable)
        self.selection_text.set(f"{selected} selected · {len(self.items)} videos found")
        idle = self.busy is None and not self.closing
        for button in (self.choose_button, self.select_button, self.clear_button):
            button.configure(state="normal" if idle else "disabled")
        self.rescan_button.configure(state="normal" if idle and self.folder else "disabled")
        self.go_button.configure(state="normal" if idle and selected else "disabled")
        self.stop_button.configure(state="normal" if self.busy == "run" and not self.stop_event.is_set() else "disabled")

    def start_batch(self):
        if self.busy:
            return
        selected = [item for item in self.items.values() if item.selectable and item.selected]
        if not selected:
            return
        self.busy = "run"
        self.stop_event = threading.Event()
        self.run_total = len(selected)
        self.run_done.clear()
        self.started_at = time.monotonic()
        self.active_key = ""
        self.video_seconds = 0
        self.progress.configure(mode="determinate", maximum=self.run_total, value=0)
        self.status_text.set(f"Starting {self.run_total} selected videos…")
        self._update_run_progress()
        self._append_log(f"\nStarting batch: {self.run_total} selected videos.")
        self._update_controls()
        work_items = [replace(item) for item in self.items.values()]

        def work():
            try:
                result = engine.run_batch(work_items, on_item=self._queue_item, on_log=self._queue_log, on_progress=self._queue_progress, stop_event=self.stop_event)
                self.events.put(("finished", result))
            except Exception as exc:
                self.events.put(("error", (str(exc), traceback.format_exc())))
        self.worker = threading.Thread(target=work, name="video-landscaper-batch", daemon=True)
        self.worker.start()

    def stop_after_current(self):
        if self.busy == "run":
            self.stop_event.set()
            self.status_text.set("Stopping after the current video finishes…")
            self._append_log("Stop requested; the active conversion and original rename will finish.")
            self._update_controls()

    def _drain_events(self):
        try:
            for _ in range(250):
                kind, payload = self.events.get_nowait()
                if kind == "item":
                    self._show_item(payload)
                elif kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    key, seconds = payload
                    item = self.items.get(key)
                    if self.busy == "run" and key == self.active_key and item is not None and item.status == "converting":
                        self.video_seconds = seconds
                elif kind == "scanned":
                    for item in payload:
                        self._show_item(item)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=1, value=0)
                    self.busy = None
                    self.status_text.set(f"Scan complete: {len(self.items)} videos found.")
                    self.progress_text.set("Select the portrait videos to convert, then click Go!" if self.items else "No decodable videos were found in this folder.")
                    self._update_controls()
                    if self.closing:
                        self.root.destroy()
                        return
                elif kind == "finished":
                    self.busy = None
                    self.started_at = None
                    self.status_text.set(payload.message)
                    self.progress_text.set(f"{payload.completed} completed · {payload.failed} failed" + (" · stopped" if payload.stopped else ""))
                    self._append_log(payload.message)
                    self._update_controls()
                    if payload.failed:
                        self.toggle_log(True)
                    if self.closing:
                        self.root.destroy()
                        return
                elif kind == "error":
                    message, details = payload
                    self.busy = None
                    self.started_at = None
                    self.progress.stop()
                    self.status_text.set("Stopped because of an error.")
                    self._append_log(details)
                    self.toggle_log(True)
                    self._update_controls()
                    if self.closing:
                        self.root.destroy()
                        return
                    messagebox.showerror("Video Landscaper", message, parent=self.root)
        except queue.Empty:
            pass
        self._schedule(70, self._drain_events)

    def _tick(self):
        if self.busy == "run":
            self._update_run_progress()
            item = self.items.get(self.active_key)
            if item is not None and item.status == "converting":
                self.tree.set(self.row_ids[self.active_key], "status", self._item_status_text(item))
        self._schedule(500, self._tick)

    def _update_run_progress(self):
        elapsed = elapsed_text(time.monotonic() - self.started_at) if self.started_at is not None else "0:00"
        self.progress_text.set(f"{len(self.run_done)} of {self.run_total} video(s) completed • Time elapsed: {elapsed}")

    def _append_log(self, text):
        lines = str(text).replace("\r\n", "\n").replace("\r", "\n")
        if not lines.endswith("\n"):
            lines += "\n"
        self.log_lines.extend(lines.splitlines(keepends=True))
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", lines)
        # Bound the live text widget and saved session log on very long batches.
        if len(self.log_lines) > 20000:
            remove = len(self.log_lines) - 20000
            del self.log_lines[:remove]
            self.log_widget.delete("1.0", f"{remove + 1}.0")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def toggle_log(self, visible=None):
        self.log_visible = not self.log_visible if visible is None else visible
        if self.log_visible:
            self.log_frame.grid()
            self.log_button.configure(text="Hide log")
        else:
            self.log_frame.grid_remove()
            self.log_button.configure(text="Show log")

    def save_log(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Save conversion log", defaultextension=".log", initialfile=f"video-landscaper-batch-{datetime.now():%Y%m%d-%H%M%S}.log", filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            try:
                Path(path).write_text("".join(self.log_lines), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Video Landscaper", f"Could not save log:\n{exc}", parent=self.root)

    def request_close(self):
        if self.closing:
            return
        if self.busy == "run":
            if not messagebox.askyesno("Finish current video?", "Stop after the current video finishes and close?\n\nThe active conversion and original-file rename will finish before closing.", parent=self.root):
                return
            self.closing = True
            self.stop_after_current()
        elif self.busy == "scan":
            self.closing = True
            self.stop_event.set()
            self.status_text.set("Stopping scan and closing…")
        else:
            self.root.destroy()
            return
        self._update_controls()

    def report_callback_exception(self, exception_type, exception, tb):
        details = "".join(traceback.format_exception(exception_type, exception, tb))
        self._append_log(details)
        self.toggle_log(True)
        messagebox.showerror("Video Landscaper", f"An interface error occurred:\n{exception}\n\nDetails are in the log.", parent=self.root)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Video Landscaper: choose and batch-convert portrait videos with a Windows GUI.")
    parser.add_argument("folder", nargs="?", type=Path, help="optional starting folder; otherwise show the folder chooser")
    args = parser.parse_args(argv)
    root = tk.Tk()
    try:
        BatchApp(root, initial_folder=args.folder)
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
