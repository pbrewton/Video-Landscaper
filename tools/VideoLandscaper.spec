# -*- mode: python ; coding: utf-8 -*-
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
import tomllib

import imageio_ffmpeg

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

# SPECPATH is supplied by PyInstaller and points to this spec's directory.
project_root = Path(SPECPATH).parent
project_metadata = tomllib.loads((project_root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
app_version = project_metadata['version']
version_pattern = r'(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})'
if not isinstance(app_version, str) or not re.fullmatch(version_pattern, app_version):
    raise SystemExit('Use a numeric MAJOR.MINOR.PATCH version in pyproject.toml for Windows builds.')
version_numbers = tuple(int(part) for part in app_version.split('.'))
if any(part > 65535 for part in version_numbers):
    raise SystemExit('Each version component in pyproject.toml must be at most 65535 for Windows builds.')
windows_version = version_numbers + (0,)
file_version = '.'.join(str(part) for part in windows_version)


def version_resource(description, internal_name):
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=windows_version, prodvers=windows_version),
        kids=[
            StringFileInfo([
                StringTable('040904B0', [
                    StringStruct('ProductName', 'Video Landscaper'),
                    StringStruct('ProductVersion', app_version),
                    StringStruct('FileVersion', file_version),
                    StringStruct('FileDescription', description),
                    StringStruct('InternalName', internal_name),
                    StringStruct('OriginalFilename', f'{internal_name}.exe'),
                    StringStruct('LegalCopyright', 'Copyright (c) 2026 Video Landscaper contributors'),
                ]),
            ]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )


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
    version=version_resource('Video Landscaper GUI', 'VideoLandscaper-gui'),
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
    version=version_resource('Video Landscaper CLI', 'VideoLandscaper-cli'),
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
