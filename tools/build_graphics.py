"""Turn graphic specs in a drop's draft.json into 1080-wide PNGs.

    python tools/build_graphics.py <drop-id> [--force]

A post (or a carousel slide) carries a spec instead of an image:

    "graphic": { "template": "compare_bars", "data": { ... } }

Templates and their data:
  stat_card     { "number": "7.4", "label": "yards per play", "context": "Ohio State offense, through week 5", "color": "#bb0000" }
  compare_bars  { "title": "Offense", "a": {"name": "Georgia"}, "b": {"name": "Alabama"},
                  "rows": [ {"label": "Points per game", "a": 34.2, "b": 38.1}, ... ] }        (4 to 8 rows; team colors looked up by name)
  trend_table   { "title": "Against the spread", "columns": ["Team", "ATS", "O/U"], "rows": [["Oregon", "4-1", "3-2"], ...] }
  rank_movers   { "title": "AP Top 25 movers", "rows": [ {"team": "Indiana", "prev": 9, "now": 7}, ... ] }
  slate_card    { "conference": "SEC", "week": 6, "games": [ {"away": "Texas", "home": "Oklahoma", "kickoff": "Sat 12:30 PM PT", "tv": "ABC", "spread": "TEX -7.5", "total": 39.5}, ... ] }
  player_card   { "name": "...", "position": "QB", "team": "Utah", "lines": ["1,234 pass yds", "11 TD, 3 INT"], "headshot_url": "https://utahutes.com/..." (optional) }

Output goes to feed/<drop-id>/img/<post-id>.png (or <post-id>-<n>.png for slides) and the
post's "image" field is set. Specs are kept in draft.json so graphics can be rebuilt.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle

from common import drop_dir, load_json, posts_file, save_json

BG, PANEL, LINE, TEXT, DIM, ACCENT = "#0f1216", "#171c22", "#2a323c", "#e8ecef", "#9aa5b1", "#34c759"
W = 10.8  # inches at dpi 100 = 1080 px


def _lum(hexcolor: str) -> float:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lighten(hexcolor: str, amt: float) -> str:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (int(c + (255 - c) * amt) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def team_color(teams: dict, name: str, fallback: str = ACCENT) -> str:
    for t in teams.values():
        if t.get("school") == name or t.get("abbr") == name:
            c = t.get("color") or ""
            alt = t.get("altColor") or ""
            c = ("#" + c) if c and not c.startswith("#") else c
            alt = ("#" + alt) if alt and not alt.startswith("#") else alt
            if c and _lum(c) >= 0.22:
                return c
            if alt and 0.22 <= _lum(alt) <= 0.9:
                return alt
            if c:
                return _lighten(c, 0.45)
    return fallback


def new_fig(height_px: int):
    fig = plt.figure(figsize=(W, height_px / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1080)
    ax.set_ylim(height_px, 0)
    ax.axis("off")
    return fig, ax


def footer(ax, h: int, note: str = "Sideline · data: ESPN"):
    ax.text(1020, h - 36, note, ha="right", va="center", color=DIM, fontsize=15)


def title(ax, text: str, y: int = 110, size: int = 40):
    ax.text(60, y, text, ha="left", va="center", color=TEXT, fontsize=size, fontweight="bold")


def save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100, facecolor=BG)
    plt.close(fig)


# ---------- templates ----------
def stat_card(d: dict, teams: dict, out: Path):
    h = 1080
    fig, ax = new_fig(h)
    color = d.get("color") or (team_color(teams, d.get("team", "")) if d.get("team") else ACCENT)
    ax.text(540, 470, str(d.get("number", "")), ha="center", va="center", color=color, fontsize=200, fontweight="bold")
    ax.text(540, 640, d.get("label", ""), ha="center", va="center", color=TEXT, fontsize=44, fontweight="bold", wrap=True)
    ax.text(540, 720, d.get("context", ""), ha="center", va="center", color=DIM, fontsize=28, wrap=True)
    footer(ax, h)
    save(fig, out)


def compare_bars(d: dict, teams: dict, out: Path):
    rows = d.get("rows", [])[:8]
    h = 300 + 130 * len(rows) + 40
    fig, ax = new_fig(h)
    a, b = d.get("a", {}), d.get("b", {})
    ca = a.get("color") or team_color(teams, a.get("name", ""), "#1f6feb")
    cb = b.get("color") or team_color(teams, b.get("name", ""), "#da3633")
    if abs(_lum(ca) - _lum(cb)) < 0.08 and ca.lower() == cb.lower():
        cb = _lighten(cb, 0.5)
    if d.get("title"):
        title(ax, d["title"])
    ax.text(60, 200, a.get("name", ""), ha="left", va="center", color=ca, fontsize=34, fontweight="bold")
    ax.text(1020, 200, b.get("name", ""), ha="right", va="center", color=cb, fontsize=34, fontweight="bold")
    y = 290
    for r in rows:
        va, vb = float(r.get("a") or 0), float(r.get("b") or 0)
        mx = max(abs(va), abs(vb)) or 1
        lower_better = bool(r.get("lowerIsBetter"))
        ax.text(540, y, r.get("label", "") + ("  (lower is better)" if lower_better else ""), ha="center", va="center", color=DIM, fontsize=24)
        # values sit at the outer edges; bars grow from the middle outward and never reach the numbers
        wa, wb = 330 * abs(va) / mx, 330 * abs(vb) / mx
        ax.add_patch(FancyBboxPatch((500 - wa, y + 22), wa, 50, boxstyle="round,pad=0,rounding_size=8", color=ca, linewidth=0))
        ax.add_patch(FancyBboxPatch((580, y + 22), wb, 50, boxstyle="round,pad=0,rounding_size=8", color=cb, linewidth=0))
        fa, fb = r.get("aDisplay", r.get("a")), r.get("bDisplay", r.get("b"))
        ax.text(60, y + 47, str(fa), ha="left", va="center", color=TEXT, fontsize=30, fontweight="bold")
        ax.text(1020, y + 47, str(fb), ha="right", va="center", color=TEXT, fontsize=30, fontweight="bold")
        y += 130
    footer(ax, h, d.get("note") or "Sideline · data: ESPN team statistics")
    save(fig, out)


def trend_table(d: dict, teams: dict, out: Path):
    cols = d.get("columns", [])
    rows = d.get("rows", [])[:12]
    h = 230 + 80 * (len(rows) + 1) + 60
    fig, ax = new_fig(h)
    if d.get("title"):
        title(ax, d["title"])
    n = max(1, len(cols))
    first_w = 400
    xs = [60] + [first_w + 60 + (960 - first_w) * (i - 1) / max(1, n - 1) for i in range(1, n)]
    y = 210
    for i, c in enumerate(cols):
        ax.text(xs[i] if i == 0 else xs[i] + (960 - first_w) / max(1, n - 1) / 2, y, str(c), ha="left" if i == 0 else "center", va="center", color=DIM, fontsize=22)
    y += 70
    for r in rows:
        ax.plot([60, 1020], [y - 40, y - 40], color=LINE, linewidth=1.5)
        for i, c in enumerate(r):
            ax.text(xs[i] if i == 0 else xs[i] + (960 - first_w) / max(1, n - 1) / 2, y, str(c), ha="left" if i == 0 else "center", va="center", color=TEXT, fontsize=28, fontweight="bold" if i == 0 else "normal")
        y += 80
    footer(ax, h, d.get("note") or "Sideline · raw numbers, no picks")
    save(fig, out)


def rank_movers(d: dict, teams: dict, out: Path):
    rows = d.get("rows", [])[:12]
    h = 230 + 86 * len(rows) + 60
    fig, ax = new_fig(h)
    title(ax, d.get("title", "Poll movers"))
    y = 220
    for r in rows:
        prev, now = r.get("prev"), r.get("now")
        up = prev is None or (isinstance(prev, (int, float)) and isinstance(now, (int, float)) and now < prev)
        out_ = now is None
        color = DIM if out_ else (ACCENT if up else "#ff453a")
        arrow = "OUT" if out_ else ("NEW" if prev in (None, 0) or (isinstance(prev, (int, float)) and prev > 25) else ("▲" if up else "▼"))
        delta = "" if out_ or arrow == "NEW" else f" {abs(int(prev) - int(now))}"
        ax.plot([60, 1020], [y - 43, y - 43], color=LINE, linewidth=1.5)
        ax.text(60, y, f"{now if now else ''}", ha="left", va="center", color=TEXT, fontsize=30, fontweight="bold")
        ax.text(140, y, str(r.get("team", "")), ha="left", va="center", color=team_color(teams, r.get("team", ""), TEXT), fontsize=30, fontweight="bold")
        ax.text(760, y, "" if prev in (None, 0) else f"was {prev}", ha="right", va="center", color=DIM, fontsize=24)
        ax.text(1020, y, f"{arrow}{delta}", ha="right", va="center", color=color, fontsize=30, fontweight="bold")
        y += 86
    footer(ax, h, d.get("note") or "Sideline · data: ESPN rankings")
    save(fig, out)


def slate_card(d: dict, teams: dict, out: Path):
    games = d.get("games", [])[:10]
    h = 230 + 112 * len(games) + 60
    fig, ax = new_fig(h)
    title(ax, f"{d.get('conference', '')} · Week {d.get('week', '')}".strip(" ·"))
    y = 215
    for g in games:
        ax.plot([60, 1020], [y - 40, y - 40], color=LINE, linewidth=1.5)
        a, hm = g.get("away", ""), g.get("home", "")
        ar = f"#{g['awayRank']} " if g.get("awayRank") else ""
        hr = f"#{g['homeRank']} " if g.get("homeRank") else ""
        ax.text(60, y, f"{ar}{a} {'vs' if g.get('neutral') else 'at'} {hr}{hm}", ha="left", va="center", color=TEXT, fontsize=30, fontweight="bold")
        ax.text(60, y + 44, " · ".join(filter(None, [g.get("kickoff", ""), g.get("tv", "")])), ha="left", va="center", color=DIM, fontsize=22)
        nums = " · ".join(filter(None, [g.get("spread", ""), f"O/U {g['total']}" if g.get("total") not in (None, "") else ""]))
        ax.text(1020, y + 22, nums, ha="right", va="center", color=DIM, fontsize=24)
        y += 112
    footer(ax, h, d.get("note") or "Sideline · schedule and lines as displayed by ESPN")
    save(fig, out)


def player_card(d: dict, teams: dict, out: Path):
    h = 1080
    fig, ax = new_fig(h)
    color = d.get("color") or team_color(teams, d.get("team", ""))
    img = None
    if d.get("headshot_url"):
        try:
            import requests
            from PIL import Image
            r = requests.get(d["headshot_url"], timeout=20)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception as e:
            print(f"    headshot skipped: {e}")
    if img is not None:
        size = 300
        img = img.resize((size, size))
        from PIL import ImageDraw
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        img.putalpha(mask)
        ax.imshow(img, extent=(540 - size / 2, 540 + size / 2, 330 + size / 2, 330 - size / 2), zorder=2)
    else:
        ax.add_patch(Circle((540, 330), 150, color=color))
        ini = "".join(w[0] for w in str(d.get("name", "?")).split()[:2]).upper()
        ax.text(540, 332, ini, ha="center", va="center", color="#ffffff", fontsize=100, fontweight="bold")
    ax.text(540, 560, d.get("name", ""), ha="center", va="center", color=TEXT, fontsize=52, fontweight="bold")
    ax.text(540, 620, " · ".join(filter(None, [d.get("position", ""), d.get("team", ""), d.get("year", "")])), ha="center", va="center", color=DIM, fontsize=28)
    y = 720
    for line in d.get("lines", [])[:5]:
        ax.text(540, y, str(line), ha="center", va="center", color=TEXT, fontsize=34)
        y += 62
    footer(ax, h, d.get("note") or "Sideline · data: ESPN")
    save(fig, out)


TEMPLATES = {"stat_card": stat_card, "compare_bars": compare_bars, "trend_table": trend_table, "rank_movers": rank_movers, "slate_card": slate_card, "player_card": player_card}


def build_one(spec: dict, teams: dict, out: Path) -> bool:
    name = spec.get("template") or spec.get("chart")
    fn = TEMPLATES.get(name)
    if not fn:
        print(f"    unknown template {name!r}")
        return False
    fn(spec.get("data", {}), teams, out)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    d = drop_dir(args.drop)
    path = posts_file(args.drop)
    data = load_json(path)
    posts = data if isinstance(data, list) else data.get("posts", [])
    teams = load_json(d / "data" / "teams.json", {})
    built = skipped = failed = 0
    for p in posts:
        targets = []
        if p.get("graphic"):
            targets.append((p, f"img/{p['id']}.png"))
        for i, s in enumerate(p.get("slides", []) or []):
            if s.get("graphic"):
                targets.append((s, f"img/{p['id']}-{i + 1}.png"))
        for holder, rel in targets:
            out = d / rel
            if out.exists() and holder.get("image") == rel and not args.force:
                skipped += 1
                continue
            try:
                if build_one(holder["graphic"], teams, out):
                    holder["image"] = rel
                    holder.setdefault("alt", holder["graphic"].get("data", {}).get("title") or holder["graphic"].get("template", "graphic"))
                    built += 1
                    print(f"  OK  {rel}")
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                print(f"  FAIL {rel}: {e}")
    save_json(path, data)
    print(f"{built} built, {skipped} unchanged, {failed} failed -> {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
