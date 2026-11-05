# Third-party notices

Video Landscaper's application source is licensed under the MIT license in
[LICENSE](LICENSE). Its packaged Windows application includes the components
below under their respective licenses. License documents are installed beside
this notice in the `licenses` folder within `_internal`.

This reference describes the Windows x64 build environment reviewed on
2026-11-05. Exact versions, the FFmpeg binary hash, and notice-file hashes are
recorded in [licenses/provenance.json](licenses/provenance.json).

## FFmpeg

- Component: unmodified `ffmpeg-win-x86_64-v7.1.exe`, supplied with
  `imageio-ffmpeg` 0.7.0.
- Reported version: `7.1-essentials_build-www.gyan.dev`.
- Copyright: FFmpeg developers and the respective authors of its components.
- License for this binary: GNU GPL version 3 or later. The executable reports
  `--enable-gpl --enable-version3` and includes statically linked libraries.
- License texts: [GPLv3](licenses/FFmpeg-COPYING.GPLv3) and
  [FFmpeg's license description](licenses/FFmpeg-LICENSE.md).
- Version, copyright, configuration, and license report:
  [FFmpeg-7.1-BUILD.txt](licenses/FFmpeg-7.1-BUILD.txt).
- Binary provider: [Gyan's 7.1 release](https://github.com/GyanD/codexffmpeg/releases/tag/7.1).
- FFmpeg source revision identified by that provider:
  [`b08d7969c550a804a59511c7b83f2dd8cc0499b8`](https://github.com/FFmpeg/FFmpeg/tree/b08d7969c550a804a59511c7b83f2dd8cc0499b8).

**Corresponding-source status is incomplete.** The upstream FFmpeg revision is
identified. Complete matching source and build materials for the statically
linked dependencies, together with their required notices, remain to be obtained
and verified before public distribution of this binary. Maintainer preparation
details are tracked in `docs/releasing.md` in the project source repository.

FFmpeg is executed as a separate command-line program. This software is based in
part on the work of the Independent JPEG Group, as acknowledged in FFmpeg's
license description.

## imageio-ffmpeg

- Version reviewed: 0.7.0.
- Copyright: 2019-2025, imageio.
- License: BSD 2-Clause.
- Full text: [imageio-ffmpeg license](licenses/imageio-ffmpeg-0.7.0-LICENSE.txt).
- Project: <https://github.com/imageio/imageio-ffmpeg>.

The FFmpeg executable supplied by this package carries its own GPL terms as
described above.

## CPython and its Windows runtime components

- Version reviewed: CPython 3.15.2, Windows x64.
- Complete distribution notice: [Python-3.15.2-LICENSE.txt](licenses/Python-3.15.2-LICENSE.txt).
- Additional notices from the installed Python documentation:
  [Python-3.15.2-THIRD-PARTY.txt](licenses/Python-3.15.2-THIRD-PARTY.txt).
- The packaging process also copies the build interpreter's original notice to
  `licenses/Python/LICENSE.txt` in the app bundle.
- Python license documentation: <https://docs.python.org/3.15/license.html>.
- Dependency version reference:
  [CPython 3.15.2 Windows build inputs](https://github.com/python/cpython/blob/v3.15.2/PCbuild/get_externals.bat).

The complete Python notice includes the PSF and historical Python license
agreements, Microsoft Distributable Code conditions, bzip2, libffi, Zstandard,
Apache 2.0 terms, and Tcl/Tk notices. The documentation snapshot includes further
acknowledgments for Python's bundled code.

Additional version-matched component documents are included for clarity:

| Component | License or notice |
| --- | --- |
| OpenSSL 3.5.9 | [Apache 2.0 license](licenses/OpenSSL-3.5.9-LICENSE.txt), [authors](licenses/OpenSSL-3.5.9-AUTHORS.md) |
| Tcl 9.0.4 | [Tcl license](licenses/Tcl-9.0.4-LICENSE.txt) |
| Tk 9.0.4 | [Tk license](licenses/Tk-9.0.4-LICENSE.txt) |
| LibTomMath supplied with Tcl | [LibTom license](licenses/LibTomMath-LICENSE.txt) |
| mpdecimal 4.0.0 | [Copyright and license](licenses/mpdecimal-4.0.0-LICENSE.txt) |
| zlib-ng 2.2.4 | [License](licenses/zlib-ng-2.2.4-LICENSE.txt) |
| liblzma from XZ Utils 5.8.1 | [0BSD license](licenses/liblzma-5.8.1-COPYING.0BSD) |

These component versions come from the CPython build reference above. Recheck
the actual runtime and its dependency inputs when changing the build interpreter.

## Packaging tools

PyInstaller builds the application bundle. Its GPL bootloader exception permits
distribution of applications under their chosen license. The reviewed 6.22.3
license and exception are included in
[PyInstaller-6.22.3-COPYING.txt](licenses/PyInstaller-6.22.3-COPYING.txt).
Its license documentation is at <https://pyinstaller.org/en/stable/license.html>.

NSIS produces the installer. Its full notice, including the licenses and
exceptions for its compression modules, is included in
[NSIS-COPYING.txt](licenses/NSIS-COPYING.txt).
Its license documentation is at <https://nsis.sourceforge.io/License>.
