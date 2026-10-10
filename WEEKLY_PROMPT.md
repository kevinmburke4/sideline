# Sideline weekly drop: the writing prompt

Paste this into Claude Code from the Sideline folder, filling in the drop id. It covers the research-and-writing step (step 1 in FEED_PLAN.md section 7). Everything else is scripted.

---

> Build the Sideline drop `2026-wNN-mon` (or `-fri`). Steps:
>
> 1. Run `python tools/fetch_espn.py 2026-wNN-mon` and read `feed/2026-wNN-mon/data/digest.md`. Use the JSON files in that folder when you need a number the digest doesn't show. Every stat, score, record, rank, line, and total in the drop must come from those files. Do not type numbers from memory. If a fact isn't in the data, leave it out or point to the ESPN link.
> 2. Write `feed/2026-wNN-mon/draft.json` following the post schema in FEED_PLAN.md section 4 and the mix below. Graphics are specs (`"graphic": {"template": ..., "data": ...}`, templates documented at the top of `tools/build_graphics.py`), audio posts carry a `"script"` field instead of a file. Team names must match ESPN's `school` spelling from `data/teams.json`. Use the ESPN `gameId` on any post about one game.
> 3. Run `python tools/run_drop.py 2026-wNN-mon --no-push`, fix whatever validate flags, then run it again without `--no-push`.
>
> Rules that never bend: no picks, predictions, leans, or projections from anyone, including you. Lines and totals appear only as the raw numbers ESPN displayed, attributed as such. No opinion about who wins. Describe what happened and what the numbers are; let the reader think.

---

## Monday drop mix (about 70 minutes, roughly 100 to 120 posts)

Tier 1, big picture (15 to 20 posts):
- One `slate` post per Power 4 conference (SEC, Big Ten, ACC, Big 12) built from `schedule.json`, plus one for notable non-conference games involving Power 4 teams or Notre Dame.
- `rankings`: an AP movers post with a `rank_movers` graphic, one post on the top five, one on who dropped out or entered. Coaches poll only if it disagrees meaningfully with AP.
- `recap`: one `audio` recap per conference (90 to 120 seconds each, scripted from `results.json`: scores, leaders, headlines), plus a short text post on the two or three biggest results with a `stat_card`.
- `around`: two or three text posts from `news.json` headlines, each with its ESPN link in `sources`. Summarize in your own words; do not reproduce article text.

Tier 2, matchups and team detail (40 to 50 posts):
- `matchup`: a `carousel` for each of the eight to ten most interesting games this week (ranked teams first, then close lines). Slides: offense `compare_bars`, defense `compare_bars`, a `stat_card` on the one number that matters, a closing slide with kickoff, TV, and the line as displayed. Caption each slide in one sentence.
- `stat-sheet`: six to eight text posts with a `compare_bars` graphic, each comparing two teams that play each other on four to six stats from `team_stats.json`. Add an `audio` version for two of them (45 to 60 seconds).
- `number`: three or four posts with `trend_table` graphics: lines and totals across the slate, biggest spreads, lowest totals, last week's results against the line as displayed. Raw numbers only, state the source. One audio clip summarizing the week's lines in 60 seconds.
- `spotlight`: three or four `player_card` posts built from the leaders in `results.json` (passing, rushing, receiving leaders from last week). Use initials unless the spec includes a headshot URL from the school's athletics site.

Tier 3, specifics (30 to 40 posts):
- `injury`: one text post per team with notable entries in `injuries.json`, grouped by game. Status wording from ESPN, nothing speculative.
- `weather`: one text post per outdoor game with a forecast in `schedule.json` (`weather` field). Skip indoor venues.
- `xpost`: entries from the curated X list, if one exists in `accounts.json` under `xaccounts`. Only the fields the schema asks for; never copy media.
- Short `text` posts with no graphic for anything else worth a sentence or two.

Audio and reading should each be about half the time. Text posts count 20 seconds, carousels 10 per slide, audio by duration.

## Friday drop mix (about 20 minutes, roughly 30 to 40 posts)

Same rules, Saturday only:
- `injury`: updated availability from a fresh `fetch_espn.py` run, one post per affected game.
- `weather`: outdoor games with a forecast, one post each, plus one `audio` summary (60 seconds).
- `number`: line movement since Monday. Compare `schedule.json` from the Monday drop folder with the fresh one; show both numbers in a `trend_table`. No commentary on why.
- `around`: late-week news from `news.json` with links.
- One updated `slate` per conference with the current numbers.

## Voice and style

- Short sentences. Plain words. Numbers over adjectives.
- Each account keeps its beat; do not have Weather Watch talk about rankings.
- Audio scripts are written to be heard: say "twenty seven to seventeen", not "27-17"; spell out team names fully the first time.
- Titles under 80 characters. Text bodies usually under 280 characters, never over 600.
- Every post with a number has a `sources` entry pointing at the ESPN page it came from.
