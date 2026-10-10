"""Render the same 20-second script in every house account's voice so they can be auditioned.

    python tools/voice_samples.py              # into the sample drop as audio posts (listen on the phone)
    python tools/voice_samples.py --out DIR    # just write DIR/<account>.mp3 files

To swap a voice, edit the "voice" field in accounts.json and re-run with --force.
Voices list: python -m edge_tts --list-voices | findstr en-US
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import FEED, accounts, load_json, render_speech, save_json, update_index_count

SCRIPT = (
    "This is a voice sample for Sideline. Georgia travels to Tuscaloosa on Saturday night, "
    "with the line sitting at Alabama minus one and a half and the total at fifty one and a half. "
    "Georgia has allowed under fifteen points a game this season, while Alabama is averaging "
    "just over seven yards a play. Kickoff is seven thirty Eastern on ABC. "
    "That is the sample. If this voice sounds right for this account, keep it. If not, swap it."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", default="sample", help="drop to add the sample posts to (default: sample)")
    ap.add_argument("--out", help="write plain MP3s to this folder instead of adding feed posts")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    acc = accounts()
    if args.out:
        out_dir = Path(args.out)
        for key, a in acc.items():
            out = out_dir / f"{key}.mp3"
            if out.exists() and not args.force:
                print(f"  skip {key}: exists"); continue
            dur = render_speech(SCRIPT, a["voice"], out)
            print(f"  OK  {key}: {a['voice']} {dur:.1f}s -> {out}")
        return 0

    drop_dir = FEED / args.drop
    posts_path = drop_dir / "posts.json"
    data = load_json(posts_path, [])
    posts = data if isinstance(data, list) else data.get("posts", [])
    by_id = {p["id"]: p for p in posts}
    for key, a in acc.items():
        pid = f"smp-v-{key}"
        rel = f"audio/voice-{key}.mp3"
        out = drop_dir / rel
        post = by_id.get(pid)
        if out.exists() and post and post.get("duration") and not args.force:
            print(f"  skip {key}: exists"); continue
        dur = render_speech(SCRIPT, a["voice"], out)
        new = {
            "id": pid, "type": "audio", "account": key, "tier": 3, "teams": ["Georgia", "Alabama"],
            "title": f"Voice sample: {a['name']}",
            "body": f"The same 20-second script read in {a['voice']}. If it does not fit {a['name']}, change the voice in accounts.json and re-run tools/voice_samples.py --force.",
            "audio": rel, "duration": int(round(dur)), "transcript": SCRIPT,
        }
        if post:
            post.update(new)
        else:
            posts.append(new)
        print(f"  OK  {key}: {a['voice']} {dur:.1f}s")
    save_json(posts_path, data if isinstance(data, list) else {**data, "posts": posts})
    update_index_count(args.drop)
    print(f"{len(acc)} voice sample posts in {posts_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
