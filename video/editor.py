import os
import re
import random
import subprocess
import tempfile
from pathlib import Path
from typing import List, Callable, Any, Optional


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

def _run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, creationflags=_NO_WINDOW)


def get_duration(path: str) -> float:
    """Return duration of media file in seconds using ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ], capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path!r}:\n{result.stderr.strip()}")
    return float(result.stdout.strip())


from utils.fonts import font_path_for as _font_path_for


def _build_overlay_cmd(concat_video: str, audio_path: str, output_path: str,
                       overlays: List[Any]) -> List[str]:
    """Build an ffmpeg command that applies overlays and merges audio."""
    text_ovs = [o for o in overlays if o.type == "text"]
    img_ovs  = [o for o in overlays if o.type == "image" and Path(o.path).exists()]

    cmd = ["ffmpeg", "-y", "-i", concat_video]
    for io in img_ovs:
        cmd += ["-i", io.path]
    cmd += ["-i", audio_path]

    audio_idx = 1 + len(img_ovs)

    if not text_ovs and not img_ovs:
        # Plain merge — re-encode video for compatibility + faststart
        cmd += ["-map", "0:v", "-map", f"{audio_idx}:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-movflags", "+faststart", "-shortest", output_path]
        return cmd

    chain = []
    cur = "0:v"
    n = 0

    for t in text_ovs:
        color = ("0x" + t.color.lstrip("#")) if t.color.startswith("#") else t.color
        font = _font_path_for(getattr(t, "font_family", "Tahoma"))
        font_part = f":fontfile='{font}'" if font else ""
        align = getattr(t, "align", "left")
        line_height = int(t.font_size * 1.4)

        # Split into lines — one drawtext filter per line (most reliable multiline method)
        lines = t.text.split("\n")
        for li, line in enumerate(lines):
            out = f"t{n}"
            txt = (line.replace("\\", "\\\\")
                       .replace("'",  "\\'")
                       .replace(":",  "\\:")
                       .replace("%",  "\\%"))
            if not txt:
                txt = " "  # empty line — keep spacing
            y_pos = t.y + li * line_height
            if align == "center":
                x_expr = "(w-text_w)/2"
            elif align == "right":
                x_expr = f"w-text_w-{t.x}"
            else:
                x_expr = str(t.x)
            chain.append(
                f"[{cur}]drawtext=text='{txt}'{font_part}"
                f":x={x_expr}:y={y_pos}:fontsize={t.font_size}:fontcolor={color}[{out}]"
            )
            cur = out
            n += 1

    for i, io in enumerate(img_ovs):
        out = f"i{n}"
        chain.append(f"[{cur}][{i + 1}:v]overlay={io.x}:{io.y}[{out}]")
        cur = out
        n += 1

    # Rename last output to [vout]
    chain[-1] = chain[-1].rsplit(f"[{cur}]", 1)[0] + "[vout]"

    cmd += [
        "-filter_complex", ";".join(chain),
        "-map", "[vout]", "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-movflags", "+faststart", "-shortest", output_path,
    ]
    return cmd


def build_video(
    audio_path: str,
    video_files: List[str],
    output_path: str,
    clip_duration: float = 5.0,
    overlays: Optional[List[Any]] = None,
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

    # Separate Main* and Plain* clips from the rest
    main_clips  = [f for f in video_files if re.match(r"(?i)main\d+",  Path(f).stem)]
    plain_clips = [f for f in video_files if re.match(r"(?i)plain\d+", Path(f).stem)]
    special     = set(main_clips) | set(plain_clips)
    other_clips = [f for f in video_files if f not in special]

    # Build clip list from non-special pool until duration is covered
    pool = list(other_clips) or list(video_files)  # fallback if no other clips
    random.shuffle(pool)
    clips = []
    total = 0.0
    while total < audio_dur:
        if not pool:
            pool = list(other_clips) or list(video_files)
            random.shuffle(pool)
        clip = pool.pop()
        clips.append(clip)
        try:
            actual = get_duration(clip)
        except Exception:
            actual = clip_duration
        total += min(clip_duration, actual)

    # Insert one random Main* clip at position 0 or 1
    if main_clips:
        main_pick = random.choice(main_clips)
        insert_pos = random.randint(0, min(1, len(clips)))
        clips.insert(insert_pos, main_pick)
        log(f"Main clip '{Path(main_pick).name}' inserted at position {insert_pos + 1}")

    # Insert one random Plain* clip at a random position
    if plain_clips:
        plain_pick = random.choice(plain_clips)
        insert_pos = random.randint(0, len(clips))
        clips.insert(insert_pos, plain_pick)
        log(f"Plain clip '{Path(plain_pick).name}' inserted at position {insert_pos + 1}")

    log(f"Selected {len(clips)} clips ({total:.1f}s) for {audio_dur:.1f}s audio")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Detect resolution from first clip to normalise all clips
        probe = subprocess.run([
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            clips[0],
        ], capture_output=True, text=True, creationflags=_NO_WINDOW)
        try:
            ref_w, ref_h = (int(x) for x in probe.stdout.strip().split(","))
        except Exception:
            ref_w, ref_h = 1080, 1920  # fallback

        # Trim + re-encode each clip so they all start at a keyframe
        # and share the same codec/resolution (required for concat -c copy)
        trimmed = []
        for i, src in enumerate(clips):
            dst = str(tmpdir_path / f"clip_{i:04d}.mp4")
            try:
                actual_dur = get_duration(src)
            except Exception:
                actual_dur = clip_duration
            trim_t = min(clip_duration, actual_dur)

            # Trim video-only (-an) — audio is irrelevant here, TTS audio is merged later.
            # Normalize fps + pixel format so concat demuxer works cleanly.
            _run([
                "ffmpeg", "-y", "-i", src,
                "-t", str(trim_t),
                "-vf", (
                    f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=decrease,"
                    f"pad={ref_w}:{ref_h}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps=30,format=yuv420p"
                ),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-an",
                "-avoid_negative_ts", "make_zero",
                dst,
            ])
            trimmed.append(dst)
            log(f"Trimmed clip {i + 1}/{len(clips)}")

        # Write concat list
        concat_list = tmpdir_path / "clips.txt"
        with open(concat_list, "w") as f:
            for p in trimmed:
                f.write(f"file '{p}'\n")

        # Concat (safe because all clips are now same codec/resolution)
        temp_concat = str(tmpdir_path / "temp_concat.mp4")
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            temp_concat,
        ])
        log("Clips concatenated")

        # Merge audio (+ apply overlays if any)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = _build_overlay_cmd(temp_concat, audio_path, output_path, overlays or [])
        _run(cmd)
        log(f"Output: {output_path}")

    return output_path
