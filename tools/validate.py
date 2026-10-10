"""Check a drop before it is published. Fails loudly.

    python tools/validate.py <drop-id> [--allow-flagged]

Checks every post against the schema in FEED_PLAN.md, that every referenced file exists and
is under size, that team names match ESPN's spelling, that tiers and ids are sane, and flags
betting-advice language. Flagged phrases fail validation unless --allow-flagged is given,
so they are always looked at by a person first.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from common import FEED, accounts, drop_dir, load_json, load_posts, posts_file, x_accounts

TYPES = {"text", "carousel", "audio", "video", "xpost", "slate"}
BANNED = re.compile(r"\b(pick|picks|lock|locks|best bet|lean|leans|leaning|projected winner|we like|i like|hammer|fade|fading|play of the (day|week)|parlay|smash|can't lose|free money|guarantee[ds]?|bet (on|the)|take the (over|under|points))\b", re.I)
LIMITS = {"image": 900_000, "audio": 4_000_000, "video": 25_000_000, "drop": 60_000_000}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    ap.add_argument("--allow-flagged", action="store_true")
    args = ap.parse_args()
    d = drop_dir(args.drop)
    path = posts_file(args.drop)
    posts = load_posts(path)
    acc = accounts()
    curated = {x["handle"].lower() for x in x_accounts()}
    teams = load_json(d / "data" / "teams.json", {})
    known_names = {t["school"] for t in teams.values()} if teams else set()
    if not known_names:
        for wk in (FEED.parent / "feed").glob("*/data/teams.json"):
            known_names |= {t["school"] for t in load_json(wk, {}).values()}
    errors, flags, warnings = [], [], []
    ids = set()
    total_bytes = 0

    def check_file(rel: str, kind: str, where: str):
        nonlocal total_bytes
        if not rel:
            errors.append(f"{where}: missing {kind} path"); return
        f = d / rel
        if not f.exists():
            errors.append(f"{where}: {kind} file not found: {rel}"); return
        size = f.stat().st_size
        total_bytes += size
        if size > LIMITS[kind]:
            errors.append(f"{where}: {kind} too large ({size // 1024} KB > {LIMITS[kind] // 1024} KB): {rel}")

    def scan(text: str, where: str):
        for m in BANNED.finditer(text or ""):
            flags.append(f"{where}: '{m.group(0)}' in: ...{text[max(0, m.start() - 40):m.end() + 40]}...")

    for p in posts:
        pid = p.get("id") or "<no id>"
        where = f"post {pid}"
        if not p.get("id"):
            errors.append("a post has no id")
        elif pid in ids:
            errors.append(f"{where}: duplicate id")
        ids.add(pid)
        t = p.get("type")
        if t not in TYPES:
            errors.append(f"{where}: bad type {t!r}"); continue
        if t != "xpost" and p.get("account") not in acc:
            errors.append(f"{where}: unknown account {p.get('account')!r}")
        if p.get("tier") not in (1, 2, 3):
            errors.append(f"{where}: tier must be 1, 2 or 3")
        for name in p.get("teams", []) or []:
            if known_names and name not in known_names:
                errors.append(f"{where}: team name {name!r} does not match ESPN's spelling")
        if t in ("text", "audio", "video", "carousel") and not p.get("title"):
            errors.append(f"{where}: {t} post needs a title")
        if t == "text":
            if not p.get("body"):
                errors.append(f"{where}: text post needs a body")
            if p.get("image"):
                check_file(p["image"], "image", where)
            if p.get("graphic") and not p.get("image"):
                errors.append(f"{where}: graphic spec not built yet (run build_graphics.py)")
        elif t == "carousel":
            slides = p.get("slides") or []
            if not 2 <= len(slides) <= 6:
                errors.append(f"{where}: carousel needs 2 to 6 slides, has {len(slides)}")
            for i, s in enumerate(slides):
                check_file(s.get("image"), "image", f"{where} slide {i + 1}")
        elif t == "audio":
            check_file(p.get("audio"), "audio", where)
            if not p.get("duration"):
                errors.append(f"{where}: audio needs duration (run tts.py)")
            if not p.get("transcript"):
                warnings.append(f"{where}: audio has no transcript")
            if p.get("image"):
                check_file(p["image"], "image", where)
        elif t == "video":
            check_file(p.get("video"), "video", where)
            check_file(p.get("poster"), "image", where)
            if not p.get("duration"):
                errors.append(f"{where}: video needs duration")
        elif t == "xpost":
            for k in ("handle", "name", "text", "url"):
                if not p.get(k):
                    errors.append(f"{where}: xpost needs {k}")
            if p.get("url") and not re.match(r"https://(x\.com|twitter\.com)/", p["url"]):
                errors.append(f"{where}: xpost url must point at x.com")
            handle = str(p.get("handle", "")).lstrip("@").lower()
            if curated and handle and handle not in curated and not handle.startswith("sample_"):
                warnings.append(f"{where}: @{handle} is not on the curated X list in accounts.json")
            if len(p.get("text") or "") > 600:
                warnings.append(f"{where}: xpost text is long ({len(p['text'])} chars); quote less")
        elif t == "slate":
            if not p.get("conference"):
                errors.append(f"{where}: slate needs conference")
            games = p.get("games") or []
            if not games:
                errors.append(f"{where}: slate has no games")
            for g in games:
                for k in ("away", "home", "kickoff"):
                    if not g.get(k):
                        errors.append(f"{where}: slate game missing {k}")
        for field in ("title", "body", "text", "script", "transcript"):
            scan(p.get(field, ""), where)
        for s in p.get("slides", []) or []:
            scan(s.get("caption", ""), where)
        if len(p.get("body") or "") > 1200:
            warnings.append(f"{where}: body is long ({len(p['body'])} chars)")

    if total_bytes > LIMITS["drop"]:
        errors.append(f"drop is {total_bytes // 1_000_000} MB, over the {LIMITS['drop'] // 1_000_000} MB limit")

    for w in warnings:
        print(f"  warn  {w}")
    for f in flags:
        print(f"  FLAG  {f}")
    for e in errors:
        print(f"  ERROR {e}")
    ok = not errors and (not flags or args.allow_flagged)
    print(f"{len(posts)} posts, {total_bytes // 1024} KB of media, {len(errors)} errors, {len(flags)} flagged phrases, {len(warnings)} warnings -> {'OK' if ok else 'FAILED'}")
    if flags and not args.allow_flagged and not errors:
        print("Flagged phrases need a human look. Edit the text, or re-run with --allow-flagged if they are fine.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
