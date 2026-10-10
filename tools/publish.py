"""Publish a drop: draft.json -> posts.json, update feed/index.json, prune old drops, commit and push.

    python tools/publish.py <drop-id> [--no-push] [--keep N]

Keeps the newest N drops (default 4) in the repo and deletes older drop folders. The
sample drop counts like any other. Run validate.py first; run_drop.py does this for you.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from common import FEED, ROOT, drop_dir, load_json, save_json

STRIP = {"graphic", "script", "notes"}  # draft-only fields that never ship


def clean_post(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k not in STRIP}
    if "slides" in out:
        out["slides"] = [{k: v for k, v in s.items() if k not in STRIP} for s in out["slides"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    ap.add_argument("--no-push", action="store_true", help="write files and commit, but do not push")
    ap.add_argument("--no-commit", action="store_true", help="write files only")
    ap.add_argument("--keep", type=int, default=4)
    args = ap.parse_args()
    d = drop_dir(args.drop)
    draft = d / "draft.json"
    src = draft if draft.exists() else d / "posts.json"
    if not src.exists():
        raise SystemExit(f"no draft.json or posts.json in {d}")
    data = load_json(src)
    posts = data if isinstance(data, list) else data.get("posts", [])
    posts = [clean_post(p) for p in posts]
    save_json(d / "posts.json", posts)

    m = re.match(r"(\d{4})-w(\d{1,2})-(mon|fri|sample)$", args.drop)
    season, week, kind = (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (None, None, "mon")
    idx_path = FEED / "index.json"
    idx = load_json(idx_path, {"drops": []})
    drops = [x for x in idx.get("drops", []) if x.get("id") != args.drop]
    existing = next((x for x in idx.get("drops", []) if x.get("id") == args.drop), None)
    published = (existing or {}).get("published") or datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(timespec="seconds")
    drops.append({"id": args.drop, "season": season, "week": week, "kind": kind, "published": published, "posts": len(posts)})
    drops.sort(key=lambda x: x.get("published") or "", reverse=True)

    removed = []
    for old in drops[args.keep:]:
        folder = FEED / old["id"]
        if folder.exists():
            shutil.rmtree(folder)
        removed.append(old["id"])
    drops = drops[:args.keep]
    idx["drops"] = drops
    save_json(idx_path, idx)
    print(f"posts.json written ({len(posts)} posts); index has {len(drops)} drops" + (f"; pruned {', '.join(removed)}" if removed else ""))

    if args.no_commit:
        return 0
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    git("add", "-A", "feed")
    status = git("status", "--porcelain", "feed")
    if not status:
        print("nothing to commit")
        return 0
    git("commit", "-q", "-m", f"Drop {args.drop}: {len(posts)} posts")
    print("committed")
    if args.no_push:
        return 0
    git("push", "-q", "origin", "main")
    print("pushed; GitHub Pages redeploys in a couple of minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
