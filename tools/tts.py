"""Render every audio post's script to MP3 with edge-tts.

    python tools/tts.py <drop-id> [--force] [--file path/to/posts.json]

Reads feed/<drop-id>/draft.json (or posts.json if there is no draft). For each post with
type "audio" and a "script" field, writes feed/<drop-id>/audio/<post-id>.mp3 using the
account's voice from accounts.json, then writes the real duration (and the transcript, if
missing) back into the post. Safe to re-run: existing clips are skipped unless --force.
"""
from __future__ import annotations

import argparse
import sys

from common import accounts, drop_dir, load_posts, posts_file, render_speech, save_json, load_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    ap.add_argument("--force", action="store_true", help="re-render clips that already exist")
    ap.add_argument("--file", help="posts file to update (default: draft.json, else posts.json)")
    args = ap.parse_args()

    path = args.file or posts_file(args.drop)
    data = load_json(path)
    posts = data if isinstance(data, list) else data.get("posts", [])
    acc = accounts()
    out_dir = drop_dir(args.drop) / "audio"
    done = skipped = failed = 0

    for p in posts:
        if p.get("type") != "audio" or not p.get("script"):
            continue
        voice = acc.get(p.get("account"), {}).get("voice")
        if not voice:
            print(f"  FAIL {p['id']}: no voice for account {p.get('account')!r}, skipping")
            failed += 1
            continue
        rel = p.get("audio") or f"audio/{p['id']}.mp3"
        out = drop_dir(args.drop) / rel
        if out.exists() and not args.force and p.get("duration"):
            skipped += 1
            continue
        try:
            dur = render_speech(p["script"], voice, out)
        except Exception as e:  # network or service error
            print(f"  FAIL {p['id']}: {e}")
            failed += 1
            continue
        p["audio"] = rel.replace("\\", "/")
        p["duration"] = int(round(dur))
        p.setdefault("transcript", p["script"])
        done += 1
        print(f"  OK  {p['id']}: {voice} {dur:.1f}s")

    save_json(path, data)
    print(f"{done} rendered, {skipped} already done, {failed} failed -> {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
