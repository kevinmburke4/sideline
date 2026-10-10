"""Stitch a video post's slides and narration into a 720x1280 MP4 with ffmpeg.

    python tools/make_video.py <drop-id> [--force]

A video post in draft.json carries "slides" (built by build_graphics.py, or plain image
paths) and a "script" (rendered to audio by tts.py). This script holds each slide for an
equal share of the audio and writes feed/<drop-id>/video/<post-id>.mp4, then sets
"video", "poster" (the first slide) and "duration" on the post. ffmpeg must be installed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from common import drop_dir, find_ffmpeg, load_json, media_duration, posts_file, save_json


def build(d, p, ffmpeg: str, out) -> float:
    slides = [s["image"] if isinstance(s, dict) else s for s in p["slides"]]
    for s in slides:
        if not (d / s).exists():
            raise FileNotFoundError(s)
    audio = d / p["audio"]
    dur = media_duration(audio)
    per = dur / len(slides)
    lst = d / "video" / f"{p['id']}.txt"
    lst.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for s in slides:
        path = str((d / s).resolve()).replace("\\", "/").replace("'", r"'\''")
        lines.append(f"file '{path}'\nduration {per:.3f}")
    lines.append(f"file '{str((d / slides[-1]).resolve()).replace(chr(92), '/')}'")  # concat demuxer needs the last frame repeated
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
           "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=#0f1216,format=yuv420p",
           "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    lst.unlink(missing_ok=True)
    return media_duration(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    d = drop_dir(args.drop)
    path = posts_file(args.drop)
    data = load_json(path)
    posts = data if isinstance(data, list) else data.get("posts", [])
    targets = [p for p in posts if p.get("type") == "video" and p.get("slides")]
    if not targets:
        print("no video posts with slides; nothing to do")
        return 0
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("ffmpeg not found; install it (winget install Gyan.FFmpeg) to build video posts")
        return 1
    done = skipped = failed = 0
    for p in targets:
        if not p.get("audio"):
            print(f"  FAIL {p['id']}: no audio yet (give it a script and run tts.py first)")
            failed += 1
            continue
        rel = f"video/{p['id']}.mp4"
        out = d / rel
        if out.exists() and p.get("video") == rel and p.get("duration") and not args.force:
            skipped += 1
            continue
        try:
            dur = build(d, p, ffmpeg, out)
        except Exception as e:
            print(f"  FAIL {p['id']}: {e}")
            failed += 1
            continue
        p["video"] = rel
        p["poster"] = p["slides"][0]["image"] if isinstance(p["slides"][0], dict) else p["slides"][0]
        p["duration"] = int(round(dur))
        done += 1
        print(f"  OK  {rel}: {dur:.1f}s, {out.stat().st_size // 1024} KB")
    save_json(path, data)
    print(f"{done} built, {skipped} unchanged, {failed} failed -> {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
