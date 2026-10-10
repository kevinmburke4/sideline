"""Run the mechanical steps for a drop in order: graphics, speech, validate, publish.

    python tools/run_drop.py <drop-id> [--fetch] [--no-push] [--allow-flagged] [--force]

The writing step produces feed/<drop-id>/draft.json first (see WEEKLY_PROMPT.md). Use
--fetch to refresh ESPN data before building (fetch also runs on its own before writing).
Stops at the first failing step.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, str(HERE / script), *args]
    print(f"\n== {script} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=HERE.parent)
    if r.returncode != 0:
        raise SystemExit(f"{script} failed (exit {r.returncode}); nothing published")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    ap.add_argument("--fetch", action="store_true", help="refresh ESPN data first")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--allow-flagged", action="store_true")
    ap.add_argument("--force", action="store_true", help="rebuild graphics and audio even if they exist")
    args = ap.parse_args()
    force = ["--force"] if args.force else []
    if args.fetch:
        run("fetch_espn.py", args.drop)
    run("build_graphics.py", args.drop, *force)
    run("tts.py", args.drop, *force)
    run("make_video.py", args.drop, *force)
    run("validate.py", args.drop, *(["--allow-flagged"] if args.allow_flagged else []))
    run("publish.py", args.drop, *(["--no-push"] if args.no_push else []))
    print("\ndrop published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
