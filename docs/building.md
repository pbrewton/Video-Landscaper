# Build the Windows app and installer

The current reviewed Windows packaging environment uses Python 3.15.2 and
imageio-ffmpeg 0.7.0. The spec checks these versions against the license reference.
The two launchers at the project root
run directly from source; these steps bundle the batch GUI for users who do not
have Python installed.

## Prepare the build environment

Open PowerShell in the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
```

The environment does not need to be activated. Commands below use its Python
explicitly. The build script uses installed dependencies and does not install or
upgrade anything itself.

## Build the app folder

```powershell
.\tools\build.ps1
```

This uses the included [PyInstaller spec](../tools/VideoLandscaper.spec)
and will generate:

```text
dist/
└── VideoLandscaper/
    ├── VideoLandscaper.exe
    └── _internal/
```

Keep this entire `VideoLandscaper` folder together. The exe needs its
`_internal` folder, including the FFmpeg bundled by `imageio-ffmpeg`. The build is
a `onedir`, windowed app, so users do not need a separate Python or FFmpeg
installation. The build script replaces an existing app bundle when rebuilding.
The project's MIT `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the `licenses` folder
are included as readable files in `_internal`. The build also includes the
interpreter's original license at `_internal/licenses/Python/LICENSE.txt`.

The spec is a maintained build configuration, written in Python. It names the GUI
launcher, collects `imageio_ffmpeg` and its FFmpeg executable, and configures the
windowed bundle. Application modules use regular package imports, so a hidden
import for the old hyphenated converter filename is no longer needed. The spec
resolves source paths relative to its own location.

To invoke PyInstaller without the `build.ps1` helper script, run this from the project root:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist --workpath build tools\VideoLandscaper.spec
```

## Build the installer

Install [NSIS](https://nsis.sourceforge.io/), then run:

```powershell
.\tools\build.ps1 -Installer
```

This rebuilds the app folder, then compiles
[installer/VideoLandscaper.nsi](../installer/VideoLandscaper.nsi). The result
is `dist\VideoLandscaper-Setup.exe`. NSIS must be in `PATH` or installed at
`C:\Program Files (x86)\NSIS`; otherwise specify its compiler path explicitly:

```powershell
.\tools\build.ps1 -Installer -MakeNsis "C:\Tools\NSIS\makensis.exe"
```

You can also compile the `.nsi` directly with NSIS after building the app folder:

```powershell
& "C:\Program Files (x86)\NSIS\makensis.exe" .\installer\VideoLandscaper.nsi
```

A welcome page waits for **Next** before copying files.
The installer copies the entire app folder `VideoLandscaper` into current user's default program folder
(e.g. `%LOCALAPPDATA%\Programs`), creates the **Video Landscaper** Start Menu shortcut, and registers a
per-user uninstaller.

## Verify and share a release

Complete the source-provision and notice review in
[releasing.md](releasing.md) before distributing Windows installers or portable
bundles publicly. The current FFmpeg dependency-source/build-material review is
incomplete.

Run the source tests before building:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Test `dist\VideoLandscaper\VideoLandscaper.exe` and the installer on Windows,
including a machine without Python or FFmpeg installed. Use copies of videos to
check conversion and original-file renaming. Check the Start Menu shortcut and
uninstaller as well.

Commit the source, `.spec`, `.nsi`, and build instructions to GitHub. Attach the
finished installer to a GitHub Release; generated `build` and `dist` folders are
excluded from source control. A portable ZIP release must contain the whole
`dist\VideoLandscaper` folder.
