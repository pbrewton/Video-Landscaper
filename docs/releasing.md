# Preparing a public Windows release

## Current status

The project includes the application MIT license, third-party notices, full
version-matched Python and imageio-ffmpeg notices, FFmpeg GPLv3 terms, and runtime
component notices. The PyInstaller spec packages these documents automatically.
NSIS copies that complete bundle into the installation.

**The current FFmpeg corresponding-source review is incomplete.** The existing
Gyan FFmpeg binary is preserved at the maintainer's request. Treat installers and
portable bundles made from it as local review builds until the items below are
resolved. The Python source repository can be committed and published during
this preparation.

## Resolve the FFmpeg materials

The exact executable and provider are recorded in
[licenses/provenance.json](../licenses/provenance.json). Its SHA-256 is
`2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`.
The version and configuration are preserved in
[FFmpeg-7.1-BUILD.txt](../licenses/FFmpeg-7.1-BUILD.txt).

1. Obtain the matching source revisions for the external libraries statically
   linked into this executable, their required license/copyright notices, any
   patches, and the scripts/configuration needed to build the combined program.
   The provider's link to the upstream FFmpeg commit identifies one part of that
   material.
2. Verify that those materials correspond to this executable. Preserve their
   origins, revisions, hashes, and build instructions.
3. Arrange durable, free download access to the complete corresponding source.
   A release source archive is one option. A third-party source server can also
   be used with clear directions and continued availability, as described in
   GPLv3 section 6(d).
4. Add the verified download locations and any remaining notices to
   [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Update the recorded status
   only after the materials and download access have been checked.

The automatically generated GitHub source ZIP covers the contents of this
application repository. FFmpeg and its dependency source materials need their
own documented download access.

References:

- [GPLv3 section 1, Corresponding Source](https://www.gnu.org/licenses/gpl-3.0.en.html#section1)
- [GPLv3 section 6, conveying executable copies](https://www.gnu.org/licenses/gpl-3.0.en.html#section6)
- [GNU guidance on source and binary downloads](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites)
- [Gyan's FFmpeg 7.1 release](https://github.com/GyanD/codexffmpeg/releases/tag/7.1)

## Keep the notices matched to the build

The current reference uses CPython 3.15.2 and imageio-ffmpeg 0.7.0. The spec
checks those versions, the actual FFmpeg binary hash, and the Python distribution
license text before packaging. A change requests a notice/provenance refresh
instead of silently using documents from a different build.

When updating dependencies, copy the complete license file from the new Python
distribution, include its applicable bundled-component notices, and replace the
imageio-ffmpeg notice with the installed distribution's version-matched text.
Review FFmpeg separately if its executable changes. Update the reference
documents and hashes in `licenses/provenance.json` after that review.

The Python reference license and documentation notices were copied from the
installed CPython 3.15.2 distribution. Additional component texts were retrieved
from the corresponding branches of
[python/cpython-source-deps](https://github.com/python/cpython-source-deps):

| Snapshot | Upstream reference |
| --- | --- |
| OpenSSL license and authors | `openssl-3.5.9` |
| Tcl and LibTomMath licenses | `tcl-9.0.4.0` |
| Tk license | `tk-9.0.4.1` |
| mpdecimal copyright | `mpdecimal-4.0.0` |
| zlib-ng license | `zlib-ng-2.2.4` |
| liblzma 0BSD text | `xz-5.8.1.1` |

License snapshots retain their text with LF line endings. File hashes in the
provenance record cover those snapshots. The runtime FFmpeg hash covers the
original executable bytes.

## Build and inspect

Once the source-provision work is complete, follow
[building.md](building.md) to run the tests and rebuild the app and installer.

Inspect `dist/VideoLandscaper/_internal` for `LICENSE`,
`THIRD_PARTY_NOTICES.md`, and the `licenses` folder. Verify that the packaged
FFmpeg executable hash matches the provenance record.

Check that `dist/VideoLandscaper` contains `VideoLandscaper-gui.exe`,
`VideoLandscaper-cli.exe`, and their shared `_internal` folder. Test the GUI's
portrait-to-landscape batch conversion and the CLI's default landscape and custom
portrait output. Test installation and uninstallation on Windows using copies of
videos. The **Video Landscaper** Start Menu shortcut should open the GUI.

Commit the source, notices, licenses, and build changes together. Attach the
`VideoLandscaper-Setup.exe` installer and any portable ZIP, plus the
corresponding-source access information, to the release tagged for that commit.
The portable ZIP must contain both executables and the shared `_internal` folder.
Keep large generated/source archives in Releases rather than the Git source history.
