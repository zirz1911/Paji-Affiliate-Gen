import os
import random
import subprocess
import tempfile
from pathlib import Path
from typing import List, Callable


def _run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def get_duration(path: str) -> float:
    """Return duration of media file in seconds using ffprobe."""
    result = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ])
    return float(result.stdout.strip())


def build_video(
    audio_path: str,
    video_files: List[str],
    output_path: str,
    clip_duration: float = 5.0,
    log: Callable[[str], None] = print,
) -> str:
    """
    Build a video by:
    1. Getting audio duration
    2. Randomly selecting/repeating video clips to match
    3. Concatenating clips
    4. Merging audio onto video
    Returns output_path on success.
    """
    if not video_files:
        raise RuntimeError("No video files found in task folder")

    audio_dur = get_duration(audio_path)
    log(f"Audio duration: {audio_dur:.1f}s")

    # Build clip list (shuffle and repeat until we have enough)
    pool = list(video_files)
    random.shuffle(pool)
    clips = []
    total = 0.0
    while total < audio_dur:
        if not pool:
            pool = list(video_files)
            random.shuffle(pool)
        clips.append(pool.pop())
        total += clip_duration

    log(f"Selected {len(clips)} clips ({total:.1f}s) for {audio_dur:.1f}s audio")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Trim each clip
        trimmed = []
        for i, src in enumerate(clips):
            dst = str(tmpdir_path / f"clip_{i:04d}.mp4")
            _run([
                "ffmpeg", "-y", "-i", src,
                "-t", str(clip_duration),
                "-c", "copy",
                dst,
            ])
            trimmed.append(dst)

        # Write concat list
        concat_list = tmpdir_path / "clips.txt"
        with open(concat_list, "w") as f:
            for p in trimmed:
                f.write(f"file '{p}'\n")

        # Concat clips
        temp_concat = str(tmpdir_path / "temp_concat.mp4")
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            temp_concat,
        ])
        log("Clips concatenated")

        # Merge audio onto video
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        _run([
            "ffmpeg", "-y",
            "-i", temp_concat,
            "-i", audio_path,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ])
        log(f"Output: {output_path}")

    return output_path
