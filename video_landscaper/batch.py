"""Video Landscaper batch discovery and recoverable file handling."""

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import threading

from . import conversion


HISTORY_NAME = ".pillarbox-batch.json"
LOCK_NAME = ".pillarbox-batch.lock"


@dataclass
class BatchItem:
    source: Path
    width: int
    height: int
    status: str = "ready"
    selected: bool = True
    detail: str = "ready to convert"
    source_size: int = 0
    source_mtime_ns: int = 0
    duration: float | None = None

    @property
    def output(self):
        return conversion.output_path_for(self.source)

    @property
    def original(self):
        return self.source.with_name(self.source.name + ".original")

    @property
    def selectable(self):
        return self.height > self.width and self.status in {"ready", "not_processed", "rename_pending"}


@dataclass(frozen=True)
class BatchResult:
    completed: int
    failed: int
    stopped: bool
    message: str


def _fingerprint(path):
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _exists(path):
    return os.path.lexists(path)


def _ffmpeg():
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Install the dependency first: py -m pip install -r requirements.txt") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _read_history(folder):
    path = folder / HISTORY_NAME
    if not _exists(path):
        return {"version": 1, "files": {}}
    if path.is_symlink():
        raise ValueError(f"Batch history must be a regular local file: {path}")
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        if history["version"] != 1 or not isinstance(history["files"], dict):
            raise ValueError("Unsupported batch history format")
        for name, record in history["files"].items():
            if Path(name).name != name or not isinstance(record, dict):
                raise ValueError("Invalid batch history entry")
            if record.get("output") != conversion.output_path_for(Path(name)).name:
                raise ValueError("Batch history output name does not match its source")
        return history
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Cannot read batch recovery history {path}: {exc}") from exc


def _write_history(folder, history):
    descriptor, name = tempfile.mkstemp(prefix=".video-landscaper-batch-", suffix=".tmp", dir=folder)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(history, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(folder / HISTORY_NAME)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _batch_lock(folder):
    """OS locks release automatically on exit, including an app crash."""
    path = folder / LOCK_NAME
    if path.is_symlink():
        raise ValueError("The batch lock must be a regular local file.")
    with path.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another batch is already running in this folder.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _can_resume(item, record):
    return (
        record.get("state") == "converted"
        and record.get("output") == item.output.name
        and not item.output.is_symlink()
        and _fingerprint(item.source) == record.get("source_fingerprint")
        and _fingerprint(item.output) == record.get("output_fingerprint")
    )


def _check_paths(item, history):
    if not item.source.is_file() or item.source.is_symlink():
        raise ValueError("Source file not found. Rescan the folder.")
    if _fingerprint(item.source) != {"size": item.source_size, "mtime_ns": item.source_mtime_ns}:
        raise ValueError("Source file changed since scanning. Rescan the folder.")
    if _exists(item.original):
        raise ValueError(f"Original backup already exists: {item.original.name}")
    if _exists(item.output):
        record = history["files"].get(item.source.name, {})
        if item.output.is_file() and _can_resume(item, record):
            return True
        raise ValueError(f"Output already exists; it cannot be confirmed as this completed conversion: {item.output.name}")
    return False


def scan_folder(folder, *, on_item=None, on_log=None, stop_event=None):
    folder = Path(folder).expanduser().resolve()
    log = on_log or (lambda message: None)
    notify = on_item or (lambda item: None)
    stop_event = stop_event or threading.Event()
    history = _read_history(folder)
    ffmpeg = _ffmpeg()
    files = sorted(
        (path for path in folder.iterdir() if path.is_file() and not path.is_symlink()
         and not path.name.lower().endswith(".original")
         and "_pillarboxed" not in path.stem.lower()
         and not path.name.lower().startswith((".pillarbox-batch", ".video-landscaper-batch"))),
        key=lambda path: path.name.casefold(),
    )
    items = []
    for index, source in enumerate(files, 1):
        if stop_event.is_set():
            break
        log(f"Inspecting {index} of {len(files)}: {source.name}")
        try:
            fingerprint = _fingerprint(source)
            info = conversion.read_video_info(
                ffmpeg, source, hide_console=True, cancel_event=stop_event,
            )
        except conversion.ConversionCancelled:
            break
        except (OSError, ValueError, RuntimeError) as exc:
            log(f"Skipped {source.name}: {exc}")
            continue
        item = BatchItem(
            source, info.width, info.height,
            source_size=fingerprint["size"], source_mtime_ns=fingerprint["mtime_ns"],
            duration=info.duration,
        )
        if info.height <= info.width:
            item.status, item.selected, item.detail = "ineligible", False, "" # alternatively, set item.detail to "skipped"
        else:
            try:
                if _check_paths(item, history):
                    item.status, item.detail = "rename_pending", "Rename failed; Press [Go!] to retry"
            except (OSError, ValueError) as exc:
                item.status, item.selected, item.detail = "conflict", False, str(exc)
        items.append(item)
        notify(item)
    # Replacing the final dot with a hyphen solves ordinary extension clashes,
    # but unusual names or extensionless videos can still converge to one name.
    groups = {}
    for item in items:
        if item.height > item.width:
            groups.setdefault(item.output.name.casefold(), []).append(item)
    for group in groups.values():
        if len(group) > 1:
            for item in group:
                item.status, item.selected = "conflict", False
                item.detail = f"Multiple source files would create {item.output.name}"
                notify(item)
    log(f"Scan finished: {len(items)} videos; {sum(item.selectable for item in items)} available for conversion.")
    return items


def rename_original(source, destination):
    if _exists(destination):
        raise FileExistsError(f"Original backup already exists: {destination.name}")
    # Path.rename refuses to overwrite an existing destination on Windows.
    source.rename(destination)


def _verify_output(ffmpeg, item, args):
    actual = conversion.read_dimensions(ffmpeg, item.output, hide_console=True)
    expected = conversion.calculate_layout(item.width, item.height, args.max_width, args.max_height)
    if actual != (expected.output_width, expected.output_height):
        raise RuntimeError(f"Output verification failed: expected {expected.output_width} x {expected.output_height}, found {actual[0]} x {actual[1]}.")


def run_batch(items, *, on_item=None, on_log=None, on_progress=None, stop_event=None):
    log = on_log or (lambda message: None)
    notify = on_item or (lambda item: None)
    stop_event = stop_event or threading.Event()
    selected = [item for item in items if item.selected and item.selectable]
    if not selected:
        return BatchResult(0, 0, False, "No videos selected.")
    folder = selected[0].source.parent
    if any(item.source.parent != folder for item in selected):
        raise ValueError("A batch must use files from one folder.")
    completed = 0
    failed = 0
    with _batch_lock(folder):
        history = _read_history(folder)
        ffmpeg = _ffmpeg()
        # Check the whole selection again before changing any files.
        destinations = set()
        for item in selected:
            try:
                if item.output.name.casefold() in destinations:
                    raise ValueError(f"Multiple selected files would create {item.output.name}")
                destinations.add(item.output.name.casefold())
                _check_paths(item, history)
            except (ValueError, OSError) as exc:
                item.status, item.selected, item.detail = "conflict", False, str(exc)
                notify(item)
                log(f"Cannot start: {item.source.name}: {exc}")
                for pending in selected:
                    if pending is not item:
                        pending.status, pending.detail = "not_processed", "Resolve the above conflict and rescan"
                        notify(pending)
                return BatchResult(0, 1, True, f"Batch did not start: {exc}")

        for item in selected:
            if stop_event.is_set():
                break
            args = conversion.ConversionOptions(input=item.source, output=item.output)
            try:
                resume = _check_paths(item, history)
                if not resume:
                    record = {
                        "state": "converting", "output": item.output.name,
                        "source_fingerprint": _fingerprint(item.source),
                    }
                    history["files"][item.source.name] = record
                    _write_history(folder, history)
                    item.status, item.detail = "converting", "Converting"
                    notify(item)
                    log(f"Converting {item.source.name} -> {item.output.name}")
                    conversion.convert(
                        args, log=log, hide_console=True,
                        source_dimensions=(item.width, item.height),
                        progress=(lambda seconds, current=item: on_progress(current, seconds)) if on_progress else None,
                    )
                item.status, item.detail = "verifying", "Checking converted video"
                notify(item)
                _verify_output(ffmpeg, item, args)
                if _fingerprint(item.source) != {"size": item.source_size, "mtime_ns": item.source_mtime_ns}:
                    raise RuntimeError("Source changed while converting; the original has not been renamed.")
                record = {
                    "state": "converted", "output": item.output.name,
                    "source_fingerprint": _fingerprint(item.source),
                    "output_fingerprint": _fingerprint(item.output),
                }
                history["files"][item.source.name] = record
                _write_history(folder, history)
                item.status, item.detail = "renaming", "Renaming original"
                notify(item)
                try:
                    rename_original(item.source, item.original)
                except OSError as exc:
                    item.status, item.selected = "rename_pending", False
                    item.detail = f"File rename failed: {exc}"
                    notify(item)
                    log(item.detail)
                    failed += 1
                    break
                # The durable "converted" record is already sufficient for
                # recovery: an absent source means renaming finished. Avoid
                # another history write after the irreversible success step.
                item.status, item.selected, item.detail = "done", False, f"Converted; original saved as {item.original.name}"
                completed += 1
                notify(item)
                log(f"Done: {item.output.name}; original: {item.original.name}")
            except (OSError, ValueError, RuntimeError) as exc:
                item.status, item.selected, item.detail = "failed", False, str(exc)
                failed += 1
                notify(item)
                log(f"Failed: {item.source.name}: {exc}")
                break
        for item in selected:
            if item.status in {"ready", "not_processed"} or (item.status == "rename_pending" and item.selected):
                # Preserve rename_pending so it remains recoverable on restart.
                if item.status != "rename_pending":
                    item.status, item.detail = "not_processed", "Not processed"
                notify(item)
    stopped = failed > 0 or stop_event.is_set()
    if failed:
        message = f"Stopped after a failure. {completed} completed; {len(selected) - completed - failed} not processed."
    elif stopped:
        message = f"Stopped as requested. {completed} completed; {len(selected) - completed} not processed."
    else:
        message = f"Batch complete. {completed} video(s) converted and originals renamed."
    log(message)
    return BatchResult(completed, failed, stopped, message)
