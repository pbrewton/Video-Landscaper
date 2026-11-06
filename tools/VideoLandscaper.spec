# -*- mode: python ; coding: utf-8 -*-
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import imageio_ffmpeg

from PyInstaller.utils.hooks import collect_all

# SPECPATH is supplied by PyInstaller and points to this spec's directory.
project_root = Path(SPECPATH).parent
license_dir = project_root / 'licenses'
provenance = json.loads((license_dir / 'provenance.json').read_text(encoding='utf-8'))

# These notices describe the reviewed Windows build. Refresh them when changing
# the runtime or bundled FFmpeg, so notices match the software being packaged.
if sys.version.split()[0] != provenance['python_version']:
    raise SystemExit('Python version changed. Refresh licenses and provenance.json before packaging; see docs/releasing.md.')
if version('imageio-ffmpeg') != provenance['imageio_ffmpeg_version']:
    raise SystemExit('imageio-ffmpeg version changed. Refresh licenses and provenance.json before packaging; see docs/releasing.md.')

ffmpeg_path = Path(imageio_ffmpeg.__file__).parent / 'binaries' / provenance['ffmpeg']['filename']
with ffmpeg_path.open('rb') as stream:
    ffmpeg_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
if ffmpeg_hash != provenance['ffmpeg']['sha256']:
    raise SystemExit('Bundled FFmpeg changed. Verify its license and matching source before updating licenses/provenance.json.')

python_license = Path(sys.base_prefix) / 'LICENSE.txt'
reference_python_license = license_dir / f"Python-{provenance['python_version']}-LICENSE.txt"
if python_license.read_text(encoding='utf-8-sig') != reference_python_license.read_text(encoding='utf-8'):
    raise SystemExit('Python license changed. Refresh the version-matched Python notices before packaging.')
datas, binaries, hiddenimports = collect_all('imageio_ffmpeg')
datas.append((str(project_root / 'LICENSE'), '.'))
datas.append((str(project_root / 'THIRD_PARTY_NOTICES.md'), '.'))
datas.append((str(license_dir), 'licenses'))
datas.append((str(python_license), 'licenses/Python'))

gui_launcher = (project_root / 'video-landscaper-batch.pyw').resolve()
cli_launcher = (project_root / 'video-landscaper-single.py').resolve()

a = Analysis(
    [str(gui_launcher), str(cli_launcher)],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Analyze dependencies once so both executables share the same Python archive,
# binaries, and data. Each executable must run only its own application launcher;
# runtime-hook scripts are common to both and must run before that launcher.
launcher_paths = {gui_launcher, cli_launcher}
runtime_scripts = [entry for entry in a.scripts if Path(entry[1]).resolve() not in launcher_paths]


def scripts_for(launcher):
    entry_points = [entry for entry in a.scripts if Path(entry[1]).resolve() == launcher]
    if len(entry_points) != 1:
        raise SystemExit(f'Expected one analyzed entry point for {launcher}; found {len(entry_points)}.')
    return runtime_scripts + entry_points


gui_exe = EXE(
    pyz,
    scripts_for(gui_launcher),
    [],
    exclude_binaries=True,
    name='VideoLandscaper-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    contents_directory='_internal',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
cli_exe = EXE(
    pyz,
    scripts_for(cli_launcher),
    [],
    exclude_binaries=True,
    name='VideoLandscaper-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    contents_directory='_internal',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    gui_exe,
    cli_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoLandscaper',
)
