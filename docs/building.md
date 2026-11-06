# Build the Windows app and installer

The current reviewed Windows packaging environment uses Python 3.15.2 and
imageio-ffmpeg 0.7.0. The spec checks these versions against the license reference.
The two launchers at the project root run directly from source. These steps
bundle both the batch GUI and single-video CLI for users who do not have Python
installed.

## Prepare the build environment

Open PowerShell in the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
```

The environment does not need to be activated. Commands below use its Python
explicitly. The build script uses installed dependencies and does not install or
upgrade anything itself.

## Set the application version

The application version is `project.version` in [pyproject.toml](../pyproject.toml).
The next release uses `0.2.0`. For future releases, edit that field and rebuild
the app and installer with `.\tools\build.ps1 -Installer`.

Use three numeric components, `MAJOR.MINOR.PATCH`, each from 0 to 65535. The
PyInstaller spec reads this value directly and embeds version information in both
executables. Version `0.2.0` maps to the Windows numeric version `0.2.0.0`.
NSIS reads the versions from the built GUI and CLI, checks that they match, and
uses the application version for the installer metadata and Installed Apps entry.

## Build the app folder

```powershell
.\tools\build.ps1
```

This uses the included [PyInstaller spec](../tools/VideoLandscaper.spec)
and will generate:

```text
dist/
└── VideoLandscaper/
    ├── VideoLandscaper-gui.exe
    ├── VideoLandscaper-cli.exe
    └── _internal/
```

Keep this entire `VideoLandscaper` folder together. Both executables use the
shared `_internal` folder, including the FFmpeg bundled by `imageio-ffmpeg`.
`VideoLandscaper-gui.exe` opens the graphical batch interface without a console.
`VideoLandscaper-cli.exe` runs the single-video converter in a console and accepts
the same options as `py video-landscaper-single.py`. The `onedir` bundle includes
Python and FFmpeg for both interfaces. The build script replaces an existing app
bundle when rebuilding.
The project's MIT `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the `licenses` folder
are included as readable files in `_internal`. The build also includes the
interpreter's original license at `_internal/licenses/Python/LICENSE.txt`.

The spec is a maintained build configuration, written in Python. It names both
source launchers, collects `imageio_ffmpeg` and its FFmpeg executable, and creates
the windowed GUI and console CLI in one app folder. Application modules use
regular package imports, so a hidden import for the old hyphenated converter
filename is no longer needed. The spec resolves source paths relative to its own
location.

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
(e.g. `%LOCALAPPDATA%\Programs`), creates the **Video Landscaper** Start Menu shortcut
that opens `VideoLandscaper-gui.exe`, and registers a per-user uninstaller.
The CLI is installed alongside the GUI.

Launch the GUI or use the CLI from PowerShell:

```powershell
& "$env:LOCALAPPDATA\Programs\VideoLandscaper\VideoLandscaper-gui.exe"
& "$env:LOCALAPPDATA\Programs\VideoLandscaper\VideoLandscaper-cli.exe" --help
& "$env:LOCALAPPDATA\Programs\VideoLandscaper\VideoLandscaper-cli.exe" "C:\Videos\portrait.mp4"
```

For landscape-to-portrait conversion with the CLI:

```powershell
& "$env:LOCALAPPDATA\Programs\VideoLandscaper\VideoLandscaper-cli.exe" "C:\Videos\landscape.mp4" --max-width 1080 --max-height 1920
```

## Verify and share a release

Complete the source-provision and notice review in
[releasing.md](releasing.md) before distributing Windows installers or portable
bundles publicly. The current FFmpeg dependency-source/build-material review is
incomplete.

Run the source tests before building:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Test both executables in `dist\VideoLandscaper` and the installer on Windows,
including a machine without Python or FFmpeg installed. Check the GUI's portrait
batch conversion and original-file renaming. Check the CLI's `--help`, default
landscape output, and custom portrait output. Use copies of videos and check the
Start Menu shortcut and uninstaller as well.

In File Explorer, right-click each GUI, CLI, and setup executable, open
**Properties → Details**, and check its product name, version, and file description.
The product version for this release is `0.2.0`. The GUI and CLI descriptions
identify their respective interfaces. After installing, confirm that Windows
**Settings → Apps → Installed apps** shows **Video Landscaper** with version `0.2.0`.

Commit the source, `.spec`, `.nsi`, and build instructions to GitHub. Attach the
finished installer to a GitHub Release; generated `build` and `dist` folders are
excluded from source control. A portable ZIP release must contain the whole
`dist\VideoLandscaper` folder.
