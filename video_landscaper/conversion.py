"""Video Landscaper conversion using FFmpeg supplied by imageio-ffmpeg."""

from dataclasses import dataclass
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time


PRESETS = (
    "ultrafast", "superfast", "veryfast", "faster", "fast", "medium",
    "slow", "slower", "veryslow",
)


@dataclass(frozen=True)
class ConversionOptions:
    """Settings shared by the command-line converter and batch GUI."""

    input: Path
    output: Path | None = None
    max_width: int = 1920
    max_height: int = 1080
    blur: float = 90
    crf: int = 18
    preset: str = "slow"
    duration: float | None = None
    audio_bitrate: str | None = None
    overwrite: bool = False


class ConversionCancelled(RuntimeError):
    """The caller stopped an unfinished operation; the original is intact."""


def _check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise ConversionCancelled("Conversion cancelled.")


def _window_options(hide_console):
    if hide_console and os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _stop_process(process):
    if process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def output_path_for(source):
    """Keep the original extension in the output name to avoid collisions."""
    source = Path(source)
    name = source.stem + "-" + source.suffix[1:] if source.suffix else source.name
    return source.with_name(name + "_pillarboxed.mp4")


@dataclass(frozen=True)
class VideoInfo:
    """Displayed video geometry and container duration in seconds, if known."""

    width: int
    height: int
    duration: float | None


@dataclass(frozen=True)
class VideoLayout:
    foreground_width: int
    foreground_height: int
    output_width: int
    output_height: int


def read_video_info(ffmpeg, source, *, hide_console=False, cancel_event=None, timeout=20):
    """Read displayed geometry and duration with one frame probe, without ffprobe.

    Duration comes from the input container's FFmpeg diagnostics. Files whose
    duration is unavailable or nonpositive retain None rather than a fake zero.
    """
    _check_cancelled(cancel_event)
    started = time.monotonic()
    with subprocess.Popen(
        [ffmpeg, "-hide_banner", "-nostdin", "-i", str(source),
         "-map", "0:V:0", "-vf", "showinfo=checksum=0", "-frames:v", "1",
         "-an", "-sn", "-dn", "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        **_window_options(hide_console),
    ) as process:
        try:
            while True:
                _check_cancelled(cancel_event)
                if timeout is not None and time.monotonic() - started >= timeout:
                    raise RuntimeError(f"FFmpeg timed out reading video dimensions after {timeout:g} seconds.")
                try:
                    _, diagnostics_bytes = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            _stop_process(process)
            process.communicate()
            raise
    _check_cancelled(cancel_event)
    diagnostics = diagnostics_bytes.decode("utf-8", errors="replace")
    if process.returncode:
        raise RuntimeError(f"FFmpeg failed while reading video dimensions:\n{diagnostics[-2000:]}")
    match = re.search(r"\bn:\s*0\s+.*?\bsar:(\d+)/(\d+)\s+s:(\d+)x(\d+)", diagnostics)
    if match is None:
        raise ValueError("Could not read the first video frame's dimensions.")
    sar_num, sar_den, width, height = map(int, match.groups())
    if sar_num and sar_den:
        # Convert non-square pixels to square pixels, rounding half upward.
        width = max(1, (2 * width * sar_num + sar_den) // (2 * sar_den))
    duration = None
    duration_match = re.search(
        r"^\s*Duration:\s*(\d+):([0-5]\d):([0-5]\d(?:\.\d+)?),",
        diagnostics, re.MULTILINE,
    )
    if duration_match is not None:
        hours, minutes, seconds = map(float, duration_match.groups())
        parsed_duration = hours * 3600 + minutes * 60 + seconds
        if math.isfinite(parsed_duration) and parsed_duration > 0:
            duration = parsed_duration
    return VideoInfo(width, height, duration)


def read_dimensions(ffmpeg, source, *, hide_console=False, cancel_event=None, timeout=20):
    """Read one decoded frame's displayed geometry, without needing ffprobe."""
    info = read_video_info(
        ffmpeg, source, hide_console=hide_console, cancel_event=cancel_event,
        timeout=timeout,
    )
    return info.width, info.height


def _run_conversion(command, *, log, progress, cancel_event, hide_console):
    """Drain both child pipes while callbacks and cancellation stay responsive."""
    events = queue.Queue()
    readers = []
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE if progress is not None else (subprocess.DEVNULL if hide_console else None),
        stderr=subprocess.PIPE if log is not None else None,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        **_window_options(hide_console),
    ) as process:
        def read_pipe(stream, kind):
            try:
                for line in stream:
                    events.put((kind, line.rstrip()))
            finally:
                stream.close()

        for stream, kind in ((process.stdout, "progress"), (process.stderr, "log")):
            if stream is not None:
                reader = threading.Thread(target=read_pipe, args=(stream, kind), daemon=True)
                reader.start()
                readers.append(reader)
        try:
            while process.poll() is None or any(reader.is_alive() for reader in readers) or not events.empty():
                _check_cancelled(cancel_event)
                try:
                    kind, line = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if kind == "log":
                    log(line)
                elif line.startswith("out_time_us="):
                    try:
                        seconds = max(0.0, int(line.partition("=")[2]) / 1_000_000)
                    except ValueError:
                        continue
                    progress(seconds)
            return process.wait()
        except BaseException:
            _stop_process(process)
            raise
        finally:
            for reader in readers:
                reader.join(timeout=2)


def calculate_layout(width, height, max_width, max_height):
    """Shrink only when necessary; add padding to approach the target ratio."""
    if width > max_width or height > max_height:
        if width * max_height >= height * max_width:
            height = max(1, height * max_width // width)
            width = max_width
        else:
            width = max(1, width * max_height // height)
            height = max_height

    # Only the encoded canvas needs even dimensions. Keep odd-sized small
    # foregrounds intact too, adding one pixel of padding where necessary.
    output_width = (width + 1) // 2 * 2
    output_height = (height + 1) // 2 * 2
    if output_width * max_height <= output_height * max_width:
        output_width = max(output_width, output_height * max_width // max_height // 2 * 2)
    else:
        output_height = max(output_height, output_width * max_height // max_width // 2 * 2)
    return VideoLayout(width, height, output_width, output_height)


def build_filter(layout, blur):
    width, height = layout.output_width, layout.output_height
    foreground = (
        f"[0:V:0]scale={layout.foreground_width}:{layout.foreground_height},setsar=1"
    )
    if (layout.foreground_width, layout.foreground_height) == (width, height):
        # Nothing needs padding, so skip the duplicate and blur work entirely.
        return foreground + "[out]"
    return (
        foreground + ",split=2[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,gblur=sigma={blur}[blurred];"
        "[blurred][fg]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1,"
        "setsar=1[out]"
    )


def convert(args, *, log=None, progress=None, cancel_event=None, source_dimensions=None, hide_console=False):
    """Convert one file; optional callbacks receive log lines and elapsed video seconds.

    Callbacks run in the calling thread. GUI callers should queue their updates
    for the UI thread. Cached source dimensions must include display rotation
    and square-pixel normalization, as returned by read_dimensions().
    """
    _check_cancelled(cancel_event)
    report = log if log is not None else lambda message: print(message, flush=True)
    source = args.input.expanduser().resolve()
    destination = (
        args.output.expanduser().resolve() if args.output
        else output_path_for(source)
    )
    if not source.is_file():
        raise ValueError(f"Input file does not exist: {source}")
    if source == destination or (destination.exists() and os.path.samefile(source, destination)):
        raise ValueError("Input and output must be different files.")
    if destination.suffix.lower() != ".mp4":
        raise ValueError("The output filename must end in .mp4.")
    if destination.exists() and (not args.overwrite or not destination.is_file()):
        raise ValueError(f"Output already exists: {destination}\nUse --overwrite to replace an output file.")
    if not destination.parent.is_dir():
        raise ValueError(f"Output folder does not exist: {destination.parent}")

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise ValueError("Install the dependency first: py -m pip install -r requirements.txt") from exc
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    report(f"Input:  {source}")
    source_width, source_height = source_dimensions or read_dimensions(
        ffmpeg, source, hide_console=hide_console, cancel_event=cancel_event,
    )
    if source_width < 1 or source_height < 1:
        raise ValueError("Video dimensions must be positive.")
    layout = calculate_layout(source_width, source_height, args.max_width, args.max_height)

    # Encode to a separate file so failed/cancelled work cannot damage an
    # existing output. Keep it on the destination volume for the final rename.
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".mp4", dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", str(source),
        "-filter_complex", build_filter(layout, args.blur),
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-crf", str(args.crf), "-preset", args.preset,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if progress is not None:
        command.extend(["-progress", "pipe:1"])
    if log is not None or progress is not None:
        command.append("-nostats")
    if args.audio_bitrate is None:
        command.extend(["-c:a", "copy"])
    else:
        command.extend(["-c:a", "aac", "-b:a", args.audio_bitrate])
    if args.duration is not None:
        command.extend(["-t", str(args.duration)])
    command.append(str(temporary))

    try:
        report(f"Output: {destination}")
        report(f"Picture: {source_width} x {source_height} -> {layout.foreground_width} x {layout.foreground_height}")
        report(f"Canvas: {layout.output_width} x {layout.output_height} (maximum {args.max_width} x {args.max_height}); blur: {args.blur}; CRF: {args.crf}")
        report("Audio:  " + (f"AAC at {args.audio_bitrate}" if args.audio_bitrate else "copy original audio"))
        report(f"FFmpeg: {ffmpeg}")
        returncode = _run_conversion(
            command, log=log, progress=progress, cancel_event=cancel_event,
            hide_console=hide_console,
        )
        if returncode:
            raise RuntimeError(f"FFmpeg failed (exit code {returncode}); see its diagnostics.")
        _check_cancelled(cancel_event)
        if args.overwrite:
            temporary.replace(destination)
        elif os.name == "nt":
            # Windows rename refuses to replace a destination that appeared
            # during encoding, preserving the no-overwrite guarantee.
            temporary.rename(destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return destination


