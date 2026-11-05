"""Launch the Video Landscaper GUI; use py.exe for console debugging."""

import os
import sys
import traceback


def main():
    try:
        from video_landscaper.gui import main as gui_main
        return gui_main()
    except Exception:
        details = traceback.format_exc()
        if sys.stderr is not None:
            print(details, file=sys.stderr)
        if os.name == "nt":
            # A startup/import error must remain visible when using pyw.exe,
            # even if tkinter itself is missing or cannot start.
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "Video Landscaper could not start.\n\n" + details, "Video Landscaper", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
