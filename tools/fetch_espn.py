"""Pull everything the writing step needs from ESPN's public JSON into feed/<drop-id>/data/.

    python tools/fetch_espn.py <drop-id>          e.g. 2026-w06-mon or 2026-w06-fri

Writes:
  data/results.json     last week's games with scores, leaders, headlines (Monday drops)
  data/schedule.json    this week's games with kickoff, TV, line, total, weather
  data/rankings.json    AP and Coaches polls with previous positions
  data/teams.json       team meta (colors, logos, conference) for every team involved
  data/team_stats.json  season statistics for Power 4 teams and Notre Dame in either week
  data/injuries.json    ESPN injury report entries for those teams
  data/news.json        recent ESPN college football headlines with links
  data/digest.md        a readable summary of all of the above for the writing step

Safe to re-run; it overwrites the data folder. Only ESPN is contacted.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from common import drop_dir, save_json

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
P4 = {"1": "ACC", "4": "Big 12", "5": "Big Ten", "8": "SEC"}
CONF = {**P4, "9": "Pac-12", "12": "C-USA", "15": "MAC", "17": "MWC", "18": "Indep.", "37": "Sun Belt", "151": "American"}
NOTRE_DAME = "87"
TZ = ZoneInfo("America/Los_Angeles")
S = requests.Session()
S.headers["User-Agent"] = "Sideline/1.0 (personal notebook)"


def get(url: str, **params):
    for attempt in range(3):
        try:
            r = S.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  retry {url}: {e}")
            time.sleep(2)


def parse_drop(drop_id: str):
    m = re.match(r"(\d{4})-w(\d{1,2})-(mon|fri|sample)$", drop_id)
    if not m:
        raise SystemExit(f"drop id must look like 2026-w06-mon or 2026-w06-fri, got {drop_id!r}")
    return int(m.group(1)), int(m.group(2)), m.group(3)


def team_obj(c: dict) -> dict:
    t = c["team"]
    rec = next((r["summary"] for r in c.get("records", []) if r.get("type") == "total"), "")
    rank = (c.get("curatedRank") or {}).get("current")
    return {
        "id": str(t["id"]), "school": t.get("location") or t.get("shortDisplayName"), "mascot": t.get("name", ""),
        "abbr": t.get("abbreviation", ""), "conf": CONF.get(str(t.get("conferenceId")), ""), "confId": str(t.get("conferenceId", "")),
        "color": t.get("color", ""), "altColor": t.get("alternateColor", ""), "logo": t.get("logo", ""),
        "rank": rank if rank and rank <= 25 else None, "record": rec,
        "score": int(c["score"]) if str(c.get("score", "")).strip() else None, "winner": bool(c.get("winner")),
        "homeAway": c.get("homeAway"),
    }


def game_obj(ev: dict) -> dict:
    comp = ev["competitions"][0]
    home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
    away = next(c for c in comp["competitors"] if c["homeAway"] == "away")
    st = comp.get("status", {}).get("type", {})
    odds = (comp.get("odds") or [{}])[0]
    kickoff = ev["date"]
    local = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(TZ)
    leaders = []
    for lt in comp.get("leaders", []):
        for ld in lt.get("leaders", [])[:1]:
            ath = ld.get("athlete", {})
            leaders.append({"category": lt.get("displayName") or lt.get("name"), "player": ath.get("displayName"),
                            "position": (ath.get("position") or {}).get("abbreviation"), "team": (ld.get("team") or {}).get("id"),
                            "line": ld.get("displayValue")})
    weather = ev.get("weather") or {}
    return {
        "gameId": str(ev["id"]), "kickoff": kickoff, "kickoffLocal": local.strftime("%a %b %-d %-I:%M %p PT") if sys.platform != "win32" else local.strftime("%a %b %d %I:%M %p PT").replace(" 0", " "),
        "name": ev.get("name"), "shortName": ev.get("shortName"), "week": (ev.get("week") or {}).get("number"),
        "state": st.get("state"), "completed": bool(st.get("completed")), "status": st.get("shortDetail", ""),
        "venue": (comp.get("venue") or {}).get("fullName", ""), "city": ", ".join(filter(None, [((comp.get("venue") or {}).get("address") or {}).get("city"), ((comp.get("venue") or {}).get("address") or {}).get("state")])),
        "indoor": bool((comp.get("venue") or {}).get("indoor")), "neutral": bool(comp.get("neutralSite")), "confGame": bool(comp.get("conferenceCompetition")),
        "tv": comp.get("broadcast", ""),
        "spread": odds.get("details", ""), "spreadNum": odds.get("spread"), "total": odds.get("overUnder"),
        "favoriteAtOpen": (odds.get("homeTeamOdds") or {}).get("favoriteAtOpen"), "homeFavorite": (odds.get("homeTeamOdds") or {}).get("favorite"),
        "weather": {"summary": weather.get("displayValue"), "tempF": weather.get("temperature"), "highF": weather.get("highTemperature")} if weather else None,
        "headline": ((comp.get("headlines") or [{}])[0]).get("shortLinkText", ""),
        "notes": [n.get("headline") for n in comp.get("notes", []) if n.get("headline")],
        "home": team_obj(home), "away": team_obj(away), "leaders": leaders,
    }


def scoreboard(season: int, week: int) -> list[dict]:
    d = get(f"{BASE}/scoreboard", groups=80, limit=400, seasontype=2, dates=season, week=week)
    return [game_obj(e) for e in d.get("events", [])]


def rankings() -> dict:
    d = get(f"{BASE}/rankings")
    out = {"week": d.get("latestWeek", {}).get("number") if isinstance(d.get("latestWeek"), dict) else None, "polls": {}}
    for poll in d.get("rankings", []):
        name = poll.get("shortName") or poll.get("name")
        if name not in ("AP Poll", "AFCA Coaches Poll", "AP Top 25", "Coaches Poll"):
            continue
        key = "ap" if "AP" in name else "coaches"
        out["polls"][key] = {
            "name": poll.get("name"), "week": (poll.get("occurrence") or {}).get("number"), "date": poll.get("date"),
            "ranks": [{"current": r["current"], "previous": r.get("previous"), "team": r["team"]["location"], "teamId": str(r["team"]["id"]),
                       "record": r.get("recordSummary"), "points": r.get("points"), "firstPlaceVotes": r.get("firstPlaceVotes")} for r in poll.get("ranks", [])],
            "others": [{"team": r["team"]["location"], "points": r.get("points")} for r in poll.get("others", [])][:10],
            "droppedOut": [{"team": r["team"]["location"], "previous": r.get("previous")} for r in poll.get("droppedOut", [])],
        }
    return out


def team_statistics(team_id: str) -> dict:
    d = get(f"{BASE}/teams/{team_id}/statistics")
    res = d.get("results") or {}
    stats = (res.get("stats") or res)
    out = {}
    for cat in stats.get("categories", []):
        out[cat["name"]] = {s["name"]: {"value": s.get("value"), "display": s.get("displayValue"), "rank": s.get("rank"), "perGame": s.get("perGameValue"), "perGameDisplay": s.get("perGameDisplayValue")} for s in cat.get("stats", [])}
    return out


def injuries(team_ids: set[str]) -> list[dict]:
    d = get(f"{BASE}/injuries")
    out = []
    for team in d.get("injuries", []):
        tid = str(team.get("id"))
        if tid not in team_ids:
            continue
        for inj in team.get("injuries", []):
            ath = inj.get("athlete", {})
            out.append({"teamId": tid, "team": team.get("displayName"), "player": ath.get("displayName"), "position": (ath.get("position") or {}).get("abbreviation"),
                        "status": inj.get("status"), "date": inj.get("date"), "detail": ((inj.get("details") or {}).get("detail") or (inj.get("details") or {}).get("type") or ""),
                        "comment": (inj.get("longComment") or inj.get("shortComment") or "")[:400]})
    return out


def news(limit: int = 15) -> list[dict]:
    d = get(f"{BASE}/news", limit=limit)
    out = []
    for a in d.get("articles", []):
        out.append({"headline": a.get("headline"), "description": a.get("description"), "published": a.get("published"),
                    "url": ((a.get("links") or {}).get("web") or {}).get("href"), "type": a.get("type")})
    return out


def pick(stats: dict, cat: str, name: str, per_game=False):
    s = (stats.get(cat) or {}).get(name) or {}
    return s.get("perGameDisplay" if per_game else "display") or s.get("display")


def val(stats: dict, cat: str, name: str):
    try:
        return float(((stats.get(cat) or {}).get(name) or {}).get("value"))
    except (TypeError, ValueError):
        return None


def team_form(games: list[dict], focus: set[str]) -> dict:
    """Season-to-date points for and against, from completed games, for the focus teams."""
    form = {}
    for g in sorted(games, key=lambda g: g["kickoff"]):
        if not g["completed"]:
            continue
        for me, opp in ((g["home"], g["away"]), (g["away"], g["home"])):
            if me["id"] not in focus or me["score"] is None or opp["score"] is None:
                continue
            f = form.setdefault(me["id"], {"games": 0, "wins": 0, "pf": 0, "pa": 0, "results": []})
            f["games"] += 1
            f["wins"] += 1 if me["winner"] else 0
            f["pf"] += me["score"]
            f["pa"] += opp["score"]
            f["results"].append({"week": g["week"], "gameId": g["gameId"], "opp": opp["school"], "oppRank": opp["rank"], "oppConf": opp["conf"],
                                 "site": "neutral" if g["neutral"] else ("home" if me["homeAway"] == "home" else "away"),
                                 "pf": me["score"], "pa": opp["score"], "won": me["winner"], "status": g["status"]})
    for f in form.values():
        f["pfPerGame"] = round(f["pf"] / f["games"], 1)
        f["paPerGame"] = round(f["pa"] / f["games"], 1)
        f["margin"] = round((f["pf"] - f["pa"]) / f["games"], 1)
    return form


def digest(season, week, kind, results, schedule, ranks, teams, team_stats, inj, headlines, form=None) -> str:
    form = form or {}
    L = [f"# Data digest · {season} week {week} · {kind} drop", ""]
    ap = (ranks.get("polls") or {}).get("ap")
    if ap:
        L += [f"## AP Top 25 (poll week {ap.get('week')})", "", "| # | Team | Prev | Record | Pts |", "|---|---|---|---|---|"]
        for r in ap["ranks"]:
            mv = "" if r["previous"] in (None, 0) else ("new" if r["previous"] > 25 else f"{r['previous']}")
            L.append(f"| {r['current']} | {r['team']} | {mv} | {r.get('record') or ''} | {r.get('points') or ''} |")
        if ap.get("droppedOut"):
            L.append("\nDropped out: " + ", ".join(f"{d['team']} (was {d['previous']})" for d in ap["droppedOut"]))
        if ap.get("others"):
            L.append("Others receiving votes: " + ", ".join(f"{o['team']} {o['points']}" for o in ap["others"]))
        L.append("")
    def is_p4(g):
        return g["home"]["confId"] in P4 or g["away"]["confId"] in P4 or NOTRE_DAME in (g["home"]["id"], g["away"]["id"])
    if results:
        L += [f"## Results · week {week - 1}", ""]
        for conf in ["SEC", "Big Ten", "ACC", "Big 12", "Other"]:
            gs = [g for g in results if is_p4(g) and (conf == "Other" and g["home"]["conf"] not in P4.values() and g["away"]["conf"] not in P4.values() or g["home"]["conf"] == conf or g["away"]["conf"] == conf)]
            if not gs:
                continue
            L.append(f"### {conf}")
            for g in sorted(gs, key=lambda g: min(g["home"]["rank"] or 99, g["away"]["rank"] or 99)):
                a, h = g["away"], g["home"]
                rk = lambda t: f"#{t['rank']} " if t["rank"] else ""
                L.append(f"- {rk(a)}{a['school']} {a['score']} at {rk(h)}{h['school']} {h['score']} ({g['status']}; line was {g['spread'] or 'n/a'}, total {g['total'] or 'n/a'}) {g['headline']}")
                if g["leaders"]:
                    L.append("  - leaders: " + "; ".join(f"{l['category']}: {l['player']} ({teams.get(l['team'], {}).get('abbr', '')}) {l['line']}" for l in g["leaders"]))
            L.append("")
    if schedule:
        L += [f"## Schedule · week {week}", ""]
        for conf in ["SEC", "Big Ten", "ACC", "Big 12", "Other"]:
            gs = [g for g in schedule if is_p4(g) and (conf == "Other" and g["home"]["conf"] not in P4.values() and g["away"]["conf"] not in P4.values() or g["home"]["conf"] == conf or g["away"]["conf"] == conf)]
            if not gs:
                continue
            L.append(f"### {conf}")
            for g in sorted(gs, key=lambda g: g["kickoff"]):
                a, h = g["away"], g["home"]
                rk = lambda t: f"#{t['rank']} " if t["rank"] else ""
                wx = f", weather {g['weather']['summary']} {g['weather']['tempF']}F" if g.get("weather") and g["weather"].get("summary") else ""
                L.append(f"- {g['gameId']} · {rk(a)}{a['school']} ({a['record']}) at {rk(h)}{h['school']} ({h['record']}) · {g['kickoffLocal']} · {g['tv']} · {g['spread'] or 'no line'} · O/U {g['total'] or 'n/a'} · {g['venue']}{', neutral' if g['neutral'] else ''}{wx}")
            L.append("")
    if team_stats:
        L += ["## Team season stats (ESPN team statistics; points allowed computed from results)", "",
              "| Team | Rec | Pts/G | Pts all/G | Margin | Yds/G | Y/play | Pass Y/G | Y/att | Rush Y/G | Y/rush | 3rd% | TO +/- | Sacks | TFL | Pen Y/G |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for tid, st in sorted(team_stats.items(), key=lambda kv: teams.get(kv[0], {}).get("school", "")):
            t = teams.get(tid, {})
            f = form.get(tid, {})
            gp = val(st, "general", "gamesPlayed") or f.get("games") or 0
            ty, plays = val(st, "rushing", "totalYards"), val(st, "rushing", "totalOffensivePlays")
            ypp = f"{ty / plays:.1f}" if ty and plays else ""
            pen = val(st, "miscellaneous", "totalPenaltyYards")
            L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                t.get("school", tid), t.get("record", ""),
                pick(st, "scoring", "totalPointsPerGame") or "",
                f.get("paPerGame", ""), f.get("margin", ""),
                pick(st, "passing", "yardsPerGame") or "", ypp,
                pick(st, "passing", "netPassingYardsPerGame") or "", pick(st, "passing", "yardsPerPassAttempt") or "",
                pick(st, "rushing", "rushingYardsPerGame") or "", pick(st, "rushing", "yardsPerRushAttempt") or "",
                pick(st, "miscellaneous", "thirdDownConvPct") or "", pick(st, "miscellaneous", "turnOverDifferential") or "",
                pick(st, "defensive", "sacks") or "", pick(st, "defensive", "tacklesForLoss") or "",
                f"{pen / gp:.1f}" if pen and gp else ""))
        L.append("")
        L += ["Stat names in team_stats.json: passing.yardsPerGame (total offense), passing.netPassingYardsPerGame, passing.yardsPerPassAttempt, passing.completionPct, rushing.rushingYardsPerGame, rushing.yardsPerRushAttempt, rushing.totalYards / rushing.totalOffensivePlays (yards per play), scoring.totalPointsPerGame, miscellaneous.thirdDownConvPct, miscellaneous.turnOverDifferential, miscellaneous.totalPenaltyYards, defensive.sacks, defensive.tacklesForLoss, defensiveInterceptions.interceptions. Points allowed and margins are in team_form.json.", ""]
    if inj:
        L += ["## Injuries (ESPN report)", ""]
        for row in sorted(inj, key=lambda r: (r["team"] or "", r["player"] or "")):
            L.append(f"- {row['team']}: {row['player']} ({row['position']}) · {row['status']} · {row['detail']} {('· ' + row['comment']) if row['comment'] else ''}")
        L.append("")
    if headlines:
        L += ["## ESPN headlines", ""]
        for a in headlines:
            L.append(f"- {a['headline']} — {a.get('description') or ''} ({a.get('url')})")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("drop")
    args = ap.parse_args()
    season, week, kind = parse_drop(args.drop)
    out = drop_dir(args.drop) / "data"
    out.mkdir(parents=True, exist_ok=True)

    print(f"schedule week {week}...")
    schedule = scoreboard(season, week)
    results = []
    season_games = []
    for w in range(1, week):
        print(f"results week {w}...")
        wk = scoreboard(season, w)
        season_games += wk
        if w == week - 1:
            results = wk
    season_games += [g for g in schedule if g["completed"]]
    print("rankings...")
    ranks = rankings()

    teams = {}
    for g in season_games + schedule:
        for t in (g["home"], g["away"]):
            teams[t["id"]] = {k: t[k] for k in ("id", "school", "mascot", "abbr", "conf", "confId", "color", "altColor", "logo", "record", "rank")}
    focus = {tid for tid, t in teams.items() if t["confId"] in P4 or tid == NOTRE_DAME}
    print(f"team stats for {len(focus)} teams...")
    team_stats = {}
    for i, tid in enumerate(sorted(focus, key=lambda x: teams[x]["school"])):
        try:
            team_stats[tid] = team_statistics(tid)
        except Exception as e:
            print(f"  stats failed for {teams[tid]['school']}: {e}")
    print("injuries, news...")
    inj = injuries(focus)
    headlines = news()

    form = team_form(season_games, focus)
    save_json(out / "schedule.json", schedule)
    save_json(out / "results.json", results)
    save_json(out / "season_games.json", season_games)
    save_json(out / "team_form.json", form)
    save_json(out / "rankings.json", ranks)
    save_json(out / "teams.json", teams)
    save_json(out / "team_stats.json", team_stats)
    save_json(out / "injuries.json", inj)
    save_json(out / "news.json", headlines)
    (out / "digest.md").write_text(digest(season, week, kind, results, schedule, ranks, teams, team_stats, inj, headlines, form), encoding="utf-8")
    print(f"done: {len(schedule)} games this week, {len(results)} last week, {len(team_stats)} team stat sheets, {len(inj)} injury rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
