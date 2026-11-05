"""Video Landscaper command-line arguments and single-video entry point."""

import argparse
import math
from pathlib import Path
import re
import sys

from .conversion import PRESETS, ConversionCancelled, ConversionOptions, convert


def _even_dimension(value):
    number = int(value)
    if number < 2 or number % 2:
        raise argparse.ArgumentTypeError("must be an even integer of at least 2")
    return number


def _blur_strength(value):
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1024:
        raise argparse.ArgumentTypeError("must be a number from 0 to 1024")
    return number


def _positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a positive number of seconds")
    return number


def _audio_bitrate(value):
    if not re.fullmatch(r"[1-9][0-9]*[kKmM]?", value):
        raise argparse.ArgumentTypeError("use a positive bitrate such as 64k or 128k")
    return value.lower()


def make_parser():
    parser = argparse.ArgumentParser(
        description="Video Landscaper: center a sharp video over a moving, blurred copy of itself.",
        epilog='Example: py video-landscaper-single.py "C:\\Videos\\portrait.mp4" --duration 10',
    )
    parser.add_argument("input", type=Path, help="source video file")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="output MP4 (default: NAME-EXT_pillarboxed.mp4 beside the source)",
    )
    parser.add_argument(
        "--max-width", type=_even_dimension, default=ConversionOptions.max_width,
        help="maximum output width; also sets target aspect ratio (default: %(default)s)",
    )
    parser.add_argument(
        "--max-height", type=_even_dimension, default=ConversionOptions.max_height,
        help="maximum output height; also sets target aspect ratio (default: %(default)s)",
    )
    parser.add_argument(
        "--blur", type=_blur_strength, default=ConversionOptions.blur,
        help="Gaussian blur strength, 0-1024 (default: %(default)s)",
    )
    parser.add_argument(
        "--crf", type=int, choices=range(0, 52), metavar="0-51",
        default=ConversionOptions.crf,
        help="H.264 quality; lower is better/larger (default: %(default)s)",
    )
    parser.add_argument(
        "--preset", choices=PRESETS, default=ConversionOptions.preset,
        help="encoding speed/compression tradeoff (default: %(default)s)",
    )
    parser.add_argument("--duration", type=_positive_seconds, help="convert only the first N seconds for a quick preview")
    parser.add_argument("--audio-bitrate", type=_audio_bitrate, metavar="RATE", help="re-encode audio to AAC at RATE, e.g. 64k (default: copy original audio)")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing output after a successful conversion")
    return parser


def main(argv=None):
    args = ConversionOptions(**vars(make_parser().parse_args(argv)))
    try:
        output = convert(args)
    except (KeyboardInterrupt, ConversionCancelled):
        print("\nConversion cancelled.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"\nSaved: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
