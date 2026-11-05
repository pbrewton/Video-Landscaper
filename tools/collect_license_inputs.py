"""Collect the licensing reference for the installed Windows build environment."""

import hashlib
from html.parser import HTMLParser
from importlib.metadata import version
import json
from pathlib import Path
import re
import subprocess
import sys

import imageio_ffmpeg


class LicenseText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and attrs.get("class") == "body" and attrs.get("role") == "main":
            self.depth = 1
        elif self.depth and tag == "div":
            self.depth += 1
        if self.depth and tag in {"p", "pre", "li", "section", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.depth and tag in {"p", "pre", "li", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")
        if self.depth and tag == "div":
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and data != "¶":
            self.parts.append(data)


root = Path(__file__).resolve().parents[1]
licenses = root / "licenses"
python_root = Path(sys.base_prefix)
parser = LicenseText()
parser.feed((python_root / "Doc/html/license.html").read_text(encoding="utf-8"))
license_text = re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip() + "\n"
assert "Stefan Krah" in license_text and "OpenSSL" in license_text
(licenses / "Python-3.15.2-THIRD-PARTY.txt").write_text(license_text, encoding="utf-8", newline="\n")

ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
report = []
for flag in ("-version", "-buildconf", "-L"):
    result = subprocess.run([str(ffmpeg), "-hide_banner", flag], check=True, capture_output=True, text=True)
    report.append(f"ffmpeg {flag}\n\n{result.stdout}{result.stderr}")
(licenses / "FFmpeg-7.1-BUILD.txt").write_text("\n\n".join(report), encoding="utf-8", newline="\n")

for path in licenses.iterdir():
    if path.is_file():
        text = path.read_text(encoding="utf-8-sig")
        path.write_text(text, encoding="utf-8", newline="\n")

with ffmpeg.open("rb") as stream:
    ffmpeg_hash = hashlib.file_digest(stream, "sha256").hexdigest()

provenance = {
    "audit_date": "2026-11-05",
    "platform": "Windows x64",
    "python_version": sys.version.split()[0],
    "imageio_ffmpeg_version": version("imageio-ffmpeg"),
    "pyinstaller_version": version("pyinstaller"),
    "python_dependencies": "https://github.com/python/cpython/blob/v3.15.2/PCbuild/get_externals.bat",
    "license_origins": {
        "Python-3.15.2-LICENSE.txt": "Copied from the build interpreter's LICENSE.txt, including its Windows binary notices.",
        "Python-3.15.2-THIRD-PARTY.txt": "Text extracted from the installed CPython 3.15.2 Doc/html/license.html main article; https://docs.python.org/release/3.15.2/license.html",
        "imageio-ffmpeg-0.7.0-LICENSE.txt": "Copied from installed imageio_ffmpeg-0.7.0.dist-info/licenses/LICENSE.",
        "FFmpeg-7.1-BUILD.txt": "Captured from the unmodified bundled executable using -version, -buildconf, and -L.",
        "FFmpeg-COPYING.GPLv3": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/b08d7969c550a804a59511c7b83f2dd8cc0499b8/COPYING.GPLv3",
        "FFmpeg-LICENSE.md": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/b08d7969c550a804a59511c7b83f2dd8cc0499b8/LICENSE.md",
        "OpenSSL-3.5.9-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython-source-deps/openssl-3.5.9/LICENSE.txt",
        "OpenSSL-3.5.9-AUTHORS.md": "https://raw.githubusercontent.com/python/cpython-source-deps/openssl-3.5.9/AUTHORS.md",
        "Tcl-9.0.4-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython-source-deps/tcl-9.0.4.0/license.terms",
        "Tk-9.0.4-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython-source-deps/tk-9.0.4.1/license.terms",
        "LibTomMath-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython-source-deps/tcl-9.0.4.0/libtommath/LICENSE",
        "mpdecimal-4.0.0-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython-source-deps/mpdecimal-4.0.0/COPYRIGHT.txt",
        "zlib-ng-2.2.4-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython-source-deps/zlib-ng-2.2.4/LICENSE.md",
        "liblzma-5.8.1-COPYING.0BSD": "https://raw.githubusercontent.com/python/cpython-source-deps/xz-5.8.1.1/COPYING.0BSD",
        "NSIS-COPYING.txt": "Copied from the installed NSIS distribution's COPYING file; https://nsis.sourceforge.io/License",
        "PyInstaller-6.22.3-COPYING.txt": "Copied from installed pyinstaller-6.22.3.dist-info/licenses/COPYING.txt.",
    },
    "ffmpeg": {
        "filename": ffmpeg.name,
        "version": "7.1-essentials_build-www.gyan.dev",
        "sha256": ffmpeg_hash,
        "license": "GPL-3.0-or-later",
        "provider_release": "https://github.com/GyanD/codexffmpeg/releases/tag/7.1",
        "ffmpeg_revision": "b08d7969c550a804a59511c7b83f2dd8cc0499b8",
        "ffmpeg_source": "https://github.com/FFmpeg/FFmpeg/tree/b08d7969c550a804a59511c7b83f2dd8cc0499b8",
        "complete_corresponding_source_status": "incomplete",
        "remaining_materials": "Matching source/revisions and build scripts for the statically linked dependencies, plus their required notices, have not been fully obtained and verified.",
    },
    "license_file_sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(licenses.iterdir()) if path.is_file() and path.name != "provenance.json"
    },
}
(licenses / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8", newline="\n")
print("Collected version-matched notice texts and FFmpeg provenance.")
print(ffmpeg_hash)
