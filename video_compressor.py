#!/usr/bin/env python3
"""
Compress 4K CCTV footage for the vehicle counting project.

Reads every .mp4 in footage/ and writes a smaller version to
compressed_footage/ using FFmpeg:

    3840x2160 -> 1280x720, 10 FPS, H.264 (CRF 25, medium preset), no audio.

Originals are never modified or deleted. Videos that have already been
compressed are skipped, so the script is safe to re-run.

Usage:
    python3 compress_videos.py
    python3 compress_videos.py --input /Volumes/drive/raw --output /Volumes/drive/small
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --- Settings -------------------------------------------------------------

# Folders are resolved relative to this script, so it can be run from anywhere.
PROJECT_DIR = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_DIR / "footage"
OUTPUT_DIR = PROJECT_DIR / "compressed_footage"

WIDTH = 1280           # target width  (down from 3840)
HEIGHT = 720           # target height (down from 2160)
FPS = 10               # target frame rate
CRF = 25               # quality: lower = better quality, bigger file
PRESET = "medium"      # encoding speed/compression trade-off


def human_size(num_bytes):
    """Turn a byte count into a readable string, e.g. 1.6 GB."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_duration(seconds):
    """Turn a number of seconds into a readable string, e.g. 2h 15m."""
    seconds = int(max(seconds, 0))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def build_command(source, destination):
    """Build the FFmpeg command for a single video."""
    return [
        "ffmpeg",
        "-hide_banner",              # skip the build-info header
        # Damaged reference frames at a recording's start produce hundreds of
        # harmless HEVC decode warnings; FFmpeg skips those frames and carries on.
        "-loglevel", "fatal",        # only problems that actually stop the encode
        "-stats",                    # live speed/time progress on stderr
        "-i", str(source),
        "-vf", f"scale={WIDTH}:{HEIGHT}",  # resize to 720p
        "-r", str(FPS),                    # drop to 10 FPS
        "-c:v", "libx264",                 # H.264 video codec
        "-crf", str(CRF),
        "-preset", PRESET,
        "-an",                             # remove the audio track
        str(destination),
    ]


def parse_arguments():
    """Allow the input and output folders to be pointed elsewhere, e.g. an external drive."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--input", type=Path, default=INPUT_DIR, help="Folder holding the source .mp4 files")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Folder to write compressed copies into")
    return parser.parse_args()


def main():
    args = parse_arguments()
    input_dir, output_dir = args.input, args.output

    # FFmpeg must be installed and on the PATH (Homebrew: brew install ffmpeg).
    if shutil.which("ffmpeg") is None:
        print("Error: FFmpeg was not found.")
        print("Install it with:  brew install ffmpeg")
        sys.exit(1)

    if not input_dir.is_dir():
        print(f"Error: input folder not found: {input_dir}")
        sys.exit(1)

    # Writing into the source folder would mix compressed files in with the originals.
    if output_dir.resolve() == input_dir.resolve():
        print("Error: output folder must be different from the input folder.")
        sys.exit(1)

    # Create the output folder if it does not exist yet.
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect the videos, sorted so the order is predictable between runs.
    videos = sorted(input_dir.glob("*.mp4"))
    if not videos:
        print(f"No .mp4 files found in {input_dir}")
        return

    total = len(videos)
    print(f"Found {total} video(s) in {input_dir}")
    print(f"Writing compressed copies to {output_dir}\n")

    compressed = 0
    skipped = 0
    failed = []
    bytes_in = 0
    bytes_out = 0
    started = time.monotonic()

    for index, source in enumerate(videos, start=1):
        destination = output_dir / source.name  # keep the original filename

        print(f"[{index}/{total}] {source.name}")

        # Skip anything that has already been compressed.
        if destination.exists():
            print("  Already compressed - skipping.\n")
            skipped += 1
            continue

        original_size = source.stat().st_size

        try:
            # check=True makes FFmpeg failures raise CalledProcessError.
            subprocess.run(build_command(source, destination), check=True)
        except subprocess.CalledProcessError as error:
            # One bad file should not stop the rest of the batch.
            print(f"  FFmpeg failed (exit code {error.returncode}) - skipping this file.\n")
            # Remove the half-written output so a re-run retries this video.
            destination.unlink(missing_ok=True)
            failed.append(source.name)
            continue
        except KeyboardInterrupt:
            # Clean up the partial file before exiting.
            destination.unlink(missing_ok=True)
            print("\nInterrupted by user.")
            sys.exit(1)

        compressed_size = destination.stat().st_size
        saved = 100 * (1 - compressed_size / original_size) if original_size else 0
        compressed += 1
        bytes_in += original_size
        bytes_out += compressed_size

        # Estimate the remaining time from the average pace so far.
        elapsed = time.monotonic() - started
        remaining = (elapsed / compressed) * (total - index)

        print(f"  {human_size(original_size)} -> {human_size(compressed_size)} ({saved:.1f}% smaller)")
        print(f"  {compressed} done, {total - index} to go · about {format_duration(remaining)} remaining\n")

    # Final summary.
    print("Done.")
    print(f"  Compressed: {compressed}")
    print(f"  Skipped:    {skipped}")
    print(f"  Failed:     {len(failed)}")
    for name in failed:
        print(f"    - {name}")
    if bytes_in:
        overall = 100 * (1 - bytes_out / bytes_in)
        print(f"  Total:      {human_size(bytes_in)} -> {human_size(bytes_out)} ({overall:.1f}% smaller)")
    print(f"  Elapsed:    {format_duration(time.monotonic() - started)}")


if __name__ == "__main__":
    main()
