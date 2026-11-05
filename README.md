# Video Landscaper

Video Landscaper converts portrait (vertical) videos to landscape (horizontal).
It keeps the original picture centered and fills the sides with a blurred copy
of the same video ([“echo” pillarboxing](https://en.wikipedia.org/wiki/Pillarbox#Stylized_pillarboxing_on_television)).
It can also convert landscape videos to portrait by adding blurred bars above & below the picture.

- **[Python command-line interface (CLI)](video-landscaper-single.py)** converts
  one video at a time and lets you choose the output aspect ratio, blur strength,
  and other settings. 
- **Windows GUI** converts batches of portrait videos to 16:9. Run the [Python script](video-landscaper-batch.pyw)
or install the app with the [Windows installer](#download-the-windows-installer).

Both interfaces use FFmpeg, supplied by the `imageio-ffmpeg` package.

## Download the Windows installer

Download `VideoLandscaper-Setup.exe` from this repository's **Releases** page. The
installer creates a **Video Landscaper** Start Menu shortcut. The installed
app includes Python and FFmpeg; users do not need to install them separately.

This source tree does not publish releases automatically. See
[Building the Windows app and installer](docs/building.md) to create a release.

## Run from Python source

Use Python 3.11 or newer on Windows, including Tkinter (included with the normal
python.org Windows installation). Only these two files are intended to be
launched directly:

| Launcher | Purpose | Command |
| --- | --- | --- |
| `video-landscaper-batch.pyw` | Select and convert one or more portrait videos in a folder | `pyw video-landscaper-batch.pyw` |
| `video-landscaper-single.py` | Convert one video with command-line options | `py video-landscaper-single.py "C:\Videos\portrait.mp4"` |

Open PowerShell in your local copy of the [project folder](/) and run the following command to install the dependency:

```powershell
py -m pip install -r requirements.txt
```

The Windows x64 wheel for `imageio-ffmpeg` includes an FFmpeg executable.
A separate system FFmpeg install is unnecessary. The script indicates the executable it uses.
The launchers import the support code in `video_landscaper`; keep that folder
beside them. Installing this project as a package is optional for running the
launchers from the source tree.

## Batch GUI

From the [project folder](/) folder, start the graphical user interface:

```powershell
pyw video-landscaper-batch.pyw
```

Use `py video-landscaper-batch.pyw` while debugging if you also want a console. Both
`py` and `pyw` commands open the same UI. (Double-clicking a `.pyw` file typically
opens the GUI without a console via `pyw.exe`/`pythonw.exe`, based on Windows file
associations.) An optional folder argument skips the initial folder chooser:
`pyw video-landscaper-batch.pyw "C:\Videos"`.

1. Choose a drive or folder at the **Choose the location of your videos** prompt.
2. The app examines files directly in that folder, without scanning subfolders.
   It asks FFmpeg whether each file has a decodable video stream; no fixed list
   of filename extensions is required. Rotation and non-square pixels are
   included in the displayed width and height.
3. Portrait videos appear blue and checked. Landscape and square videos appear
   gray without checkboxes. Click checkboxes or press Space on a selected row;
   **Select all** and **Clear selection** affect only eligible rows.
4. Click **Go!** to convert the selected files sequentially, with the same
   defaults as the command-line converter: maximum 1920 x 1080, blur 90,
   preset slow, CRF 18, and original audio copied.
5. After conversion, the app checks that the output's first video frame is
   readable and that its dimensions match the expected canvas. It then appends
   `.original` to the original filename. The row turns green and loses its
   checkbox only after the rename succeeds.

Output names retain the input extension by replacing its last separating dot
with a hyphen:

| Source | Converted output | Renamed original |
| --- | --- | --- |
| `holiday.mov` | `holiday-mov_pillarboxed.mp4` | `holiday.mov.original` |
| `holiday.mp4` | `holiday-mp4_pillarboxed.mp4` | `holiday.mp4.original` |
| `family.trip.mov` | `family.trip-mov_pillarboxed.mp4` | `family.trip.mov.original` |

The app flags conflicting output and original-backup filenames before starting.
It never overwrites them. An encoder, output-verification, or original-rename
failure turns that row red and stops the batch; remaining selections say
**Not processed**. **Show log** displays FFmpeg messages inside the app, and
**Save log** exports them. No separate FFmpeg console windows are opened.

**Stop after current video** allows the active conversion and original rename
to finish, then stops before the next file. Closing during conversion offers
the same behavior. Scanning can be stopped by closing the window.

If conversion succeeds but renaming the original fails, the app retains both
files. Select that red row and click **Go!** to retry just the rename, or reopen
the folder later. The app uses `.pillarbox-batch.json` beside the videos to
recognize verified outputs using source/output sizes and modification times.
Keep that recovery file if a rename is pending. Modified files are flagged as
conflicts instead of being trusted automatically. An interrupted conversion
whose completion was not recorded is also flagged if an output exists.

The `.pillarbox-batch.lock` file prevents two app instances from converting the
same folder simultaneously. Its OS lock releases when the app exits, including
after a crash; the small lock file itself can remain. Generated outputs,
`.original` backups, recovery files, temporary outputs, and symbolic links are
excluded from video discovery. Rescan refreshes the folder contents.

Original files are renamed only by the batch GUI. The command-line converter
below continues to preserve the original filename. The GUI uses the converter's
Python function directly, so Python settings and FFmpeg processing are shared.

## Convert a video

```powershell
py video-landscaper-single.py "C:\Videos\portrait.mp4"
```

Creates `C:\Videos\portrait-mp4_pillarboxed.mp4`. Use quotes around paths with spaces.
The default output is an MP4 with H.264 video, with a maximum size of 1920 x 1080
and a target aspect ratio of 16:9. Original audio streams
are copied without re-encoding, preserving the compressed audio and its bitrate.
Videos without audio are supported too.

The original picture is centered and kept whole. If either displayed source
dimension exceeds its maximum, the clear picture is scaled down proportionally
to fit. Otherwise its dimensions stay unchanged; it is never scaled up.
The canvas is then extended to the target ratio by adding blurred side bars
or top/bottom bars. A duplicate fills the background, is cropped, and blurred;
both copies move together. If no bars are needed, the duplicate and blur work
are skipped.

`--max-width : --max-height` sets both the maximum bounds and the target ratio.
For H.264 compatibility the output dimensions must be even. The added dimension
is rounded down to an even number, without cropping the clear picture, so the
ratio can differ slightly from the target. Odd-sized clear pictures are kept
intact, with the canvas padded to even dimensions. Resizing larger pictures also
requires rounding to whole pixels.

Examples with the default maximum of 1920 x 1080:

| Displayed input | Clear picture | Output canvas |
| --- | --- | --- |
| 160 x 90 | 160 x 90 | 160 x 90 |
| 90 x 160 | 90 x 160 | 284 x 160 |
| 100 x 100 | 100 x 100 | 176 x 100 |
| 320 x 90 | 320 x 90 | 320 x 180 |
| 3840 x 2160 | 1920 x 1080 | 1920 x 1080 |
| 720 x 1280 | 607 x 1080 | 1920 x 1080 |

The script reads one decoded frame to determine displayed dimensions, including
phone rotation and non-square pixels, using the bundled FFmpeg; ffprobe is not
required. The script does not impose a new frame rate. Non-square pixels are
converted to square pixels for correct display proportions.

## Quick preview and settings

Convert only the first 10 seconds and save to a different filename:

```powershell
py video-landscaper-single.py "C:\Videos\portrait.mp4" -o "C:\Videos\preview.mp4" --duration 10
```

Try a 1280 x 720 maximum and faster encoding:

```powershell
py video-landscaper-single.py "C:\Videos\portrait.mp4" --max-width 1280 --max-height 720 --preset fast
```

Available settings:

| Option | Default | Meaning |
| --- | --- | --- |
| `-o`, `--output` | Beside input, as `NAME-EXT_pillarboxed.mp4` | Destination MP4; its folder must exist |
| `--max-width` | `1920` | Maximum output width; positive even integer; sets target ratio with max-height |
| `--max-height` | `1080` | Maximum output height; positive even integer; sets target ratio with max-width |
| `--blur` | `90` | Gaussian blur strength, 0-1024; higher is blurrier |
| `--crf` | `18` | H.264 quality, 0-51; lower gives higher quality and larger files |
| `--preset` | `slow` | Encoder speed/compression tradeoff; try `fast` or `veryfast` |
| `--duration` | Entire video | Convert the first N seconds |
| `--audio-bitrate` | Copy original audio | Set e.g. `64k` to re-encode audio to AAC at a target bitrate per stream |
| `--overwrite` | Off | Replace an existing output only after successful encoding |

The previous `--width` and `--height` options have been replaced by
`--max-width` and `--max-height`.

Copying audio avoids another lossy encoding pass. Reported average bitrate can
still vary slightly with container metadata or when making a short preview.
If the original audio codec cannot be stored in MP4, FFmpeg reports an error;
retry with `--audio-bitrate 128k` (or your chosen rate) to encode compatible AAC.
An AAC target bitrate is approximate, so a `64k` target may not report exactly 64 kb/s.

FFmpeg shows conversion progress in the terminal. Press Ctrl+C to cancel.
The source is preserved. Temporary output is cleaned up after an ordinary error
or cancellation. Existing output is protected unless `--overwrite` is supplied.

This baseline targets SDR video. HDR-to-SDR tone mapping is not implemented yet;
HDR phone footage needs a separate color-handling pass before relying on its colors.
Subtitles and data tracks are not copied.

## Help and verification

```powershell
py video-landscaper-single.py --help
py -m unittest -v
# The explicit equivalent:
py -m unittest discover -s tests -t . -v
```

The tests generate short synthetic clips and use the package's FFmpeg to convert
and decode them. Batch tests cover conflicts, output verification, failed renames,
recovery, stopping, and folder locking; GUI tests use isolated synthetic rows.
No personal videos or system FFmpeg are required.

GitHub Actions runs this test suite on Windows with Python 3.11 and 3.15 for pushes
and pull requests.

## Repository layout

```text
video-landscaper-single.py       Single-video launcher
video-landscaper-batch.pyw       Batch GUI launcher
video_landscaper/                Imported application code
    __init__.py
    conversion.py               FFmpeg, sizing, audio, progress
    cli.py                      Command-line arguments and main function
    batch.py                    Scanning, conflicts, recovery, renaming
    gui.py                      Tkinter interface
tests/                          Automated tests, discovered by unittest
installer/
    VideoLandscaper.nsi          Per-user NSIS installer
tools/
    VideoLandscaper.spec         PyInstaller bundle configuration
    build.ps1                   Windows build helper
docs/
    building.md                 EXE and installer instructions
.github/workflows/tests.yml     Windows test workflow
pyproject.toml                  Package metadata and dependency declaration
requirements.txt               Runtime dependency for source users
LICENSE                        MIT license for the project source
```

The package uses normal Python imports. Support modules and tests are kept in
their folders rather than exposed as additional launchers. This flat layout lets
both launchers work immediately from a checkout after installing the dependency.

Build output, virtual environments, Python caches, and local video files are
excluded by `.gitignore`. Keep generated installers in GitHub Releases rather
than committing them to the source repository. See
[docs/building.md](docs/building.md) for build and release instructions.

## License

The Video Landscaper source code is available under the [MIT License](LICENSE).

Packaged third-party components have their own licenses, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The remaining FFmpeg
corresponding-source work for a public Windows binary release is tracked in
[the release preparation notes](docs/releasing.md).

References: [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg),
[FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html).
