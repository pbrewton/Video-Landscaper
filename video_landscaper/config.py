"""Shared, per-user encoding settings loaded when an interface starts."""

import configparser
from dataclasses import dataclass
from importlib import resources
import os
from pathlib import Path
import sys


CONFIG_FILENAME = "VideoLandscaper.ini"


@dataclass(frozen=True)
class EncodingSettings:
    """An immutable snapshot so edits cannot change a running batch."""

    legacy_tv_compatibility: bool = False


def default_config_path():
    """Return the settings file shared by the GUI, CLI, and source launchers."""
    if sys.platform == "win32":
        base = Path(os.environ["APPDATA"]) if os.environ.get("APPDATA") else Path.home() / "AppData" / "Roaming"
    else:
        base = Path(os.environ["XDG_CONFIG_HOME"]) if os.environ.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / "VideoLandscaper" / CONFIG_FILENAME


def load_settings(path=None):
    """Create defaults if needed, then read one settings snapshot.

    Existing files are never rewritten. An explicit path is useful to callers
    embedding the converter and keeps tests independent of the user's profile.
    Invalid settings and access errors identify the file instead of silently
    disabling a setting the user intended to enable.
    """
    path = Path(path) if path is not None else default_config_path()
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            template = resources.files(__package__).joinpath(CONFIG_FILENAME).read_text(encoding="utf-8")
            try:
                with path.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(template)
            except FileExistsError:
                # Another interface may have created the shared file first.
                pass
        contents = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise OSError(f"Unable to read or create settings file {path}: {exc}") from exc
    except UnicodeError as exc:
        raise ValueError(f"Invalid settings file {path}: save the file as UTF-8 ({exc})") from exc

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(contents, source=str(path))
        enabled = parser.getboolean("Encoding", "legacy_tv_compatibility", fallback=False)
    except (configparser.Error, ValueError) as exc:
        raise ValueError(f"Invalid settings file {path}: {exc}") from exc
    return EncodingSettings(legacy_tv_compatibility=enabled)
