# Sideline Feed: Build Spec

**For Claude Code.** This adds a Feed tab to the existing Sideline web app. Read this whole file, then read `README.md` and `app.js` before writing any code.

---

## 1. What this is

A scrollable college football feed inside Sideline that replaces my phone scrolling time. Think of an X timeline built only for Power 4 college football: short posts with graphics, swipeable carousels, short audio clips, the occasional narrated video, and posts pulled from a curated list of X accounts.

New content drops twice a week:

- **Monday drop (about 70 minutes of content):** last week's recaps, rankings movement, team and matchup stat comparisons for the coming week, spread and total trends, player spotlights, the slate by conference.
- **Friday drop (about 20 minutes):** injuries and availability, weather for outdoor games, line movement, late-week news, all focused on Saturday.

About half the time should be reading and half listening.

The content is made outside the app (see section 7) and pushed to the GitHub repo as a "drop" folder. The app never generates content. It only reads and displays drops.

**Non-goals:** no betting picks, predictions, leans, or projections from anyone, including generated content. Lines and trend records are shown as raw numbers only. No accounts, no backend, no API keys in the app.

---

## 2. Constraints from the existing app (do not break these)

Sideline is a no-build static web app (`index.html`, `app.js`, `styles.css`, `sw.js`) hosted on GitHub Pages at `https://kevinmburke4.github.io/sideline/` and saved to my iPhone home screen. It already works and holds my notes.

1. **Never touch `sideline.v1` in localStorage** or the `sideline.wk.*` cache keys except through existing code. My notes live there and exist only on my phone. Feed state gets its own key, `sideline.feed.v1`, and must stay small (read/played IDs only, never post content).
2. **The URL and origin must not change.** A new origin means empty storage and lost notes.
3. **Keep it no-build.** Plain JS, no framework, no bundler. A new `feed.js` file loaded after `app.js` is fine and preferred, so the feed is a separate module.
4. **Leave the Games, Teams, Notes, and More tabs working exactly as they do now.** Add a fifth tab, Feed, and make it the first tab. Keep Games as the default route until I say otherwise.
5. **Service worker:** bump `VERSION` so phones pick up the new shell. Add `feed.js` to `SHELL`. Do not let the service worker cache audio or video files (they would fill storage); cache drop JSON and images network-first like everything else.
6. Before the first deploy, add a line to the More tab reminding me to export notes, and do not ship anything that clears storage.

---

## 3. Content layout in the repo

```
feed/
  index.json                 list of drops, newest first
  2026-w08-mon/
    posts.json               every post in this drop
    img/                     PNG graphics (1080 wide)
    audio/                   MP3 clips (mono, 64 kbps)
    video/                   MP4 (720x1280, H.264, short)
  2026-w08-fri/
    ...
accounts.json                the 10 house accounts (names, voices, colors)
tools/                       content pipeline scripts (run on my PC, not in the app)
```

`feed/index.json`:

```json
{
  "drops": [
    { "id": "2026-w08-fri", "season": 2026, "week": 8, "kind": "fri", "published": "2026-10-16T15:00:00-07:00", "posts": 34 },
    { "id": "2026-w08-mon", "season": 2026, "week": 8, "kind": "mon", "published": "2026-10-12T18:00:00-07:00", "posts": 118 }
  ]
}
```

Keep the last 4 drops in the repo. A tools script deletes older drop folders so the repo stays well under GitHub Pages' size limit.

---

## 4. Post schema

Every post in `posts.json` has these common fields:

```json
{
  "id": "w08m-0042",
  "type": "text | carousel | audio | video | xpost | slate",
  "account": "stat-sheet",
  "tier": 1,
  "teams": ["Utah", "BYU"],
  "gameId": "401752xxx",
  "title": "Utah's run defense is the best it has been in a decade",
  "body": "Short post text. Plain text, no markdown. Usually under 280 characters for text posts.",
  "sources": [{ "label": "ESPN team stats", "url": "https://..." }]
}
```

- `account`: a house account key from `accounts.json`, or the X handle for `xpost`.
- `tier`: 1 = big picture, 2 = matchups and team detail, 3 = specifics and deep dives. Drives feed order (section 5).
- `teams`: school names exactly as ESPN's feed uses them, so the app can link posts to Sideline's team pages and my notes.
- `gameId`: the ESPN event ID when the post is about one game, so it can link to the game page. Optional.

Type-specific fields:

| Type | Extra fields | How it renders |
|---|---|---|
| `text` | `image` (path), `alt` | Avatar, account name, text, one graphic below |
| `carousel` | `slides`: array of `{ image, alt, caption }`, 2 to 6 | Horizontal swipe with scroll-snap and dot indicators |
| `audio` | `audio` (path), `duration` (seconds), `transcript`, optional `image` | Card with play button, progress bar, duration; transcript collapsed under "Read along" |
| `video` | `video` (path), `poster` (image), `duration` | Inline player, tap to play, no autoplay with sound |
| `xpost` | `handle`, `name`, `postedAt`, `text`, `url`, `hasMedia` | Styled like an X post. Tapping opens the original on x.com. Never copy X media; if `hasMedia` is true show "Photo or video on X" |
| `slate` | `conference`, `games`: array of `{ gameId, away, home, kickoff, tv, spread, total }` | Compact schedule card for one conference. Each row links to the Sideline game page |

---

## 5. Feed behavior

- **Order:** posts from the newest drop first. Within a drop, show all tier 1 posts, then tier 2, then tier 3. Shuffle within each tier, using a seed based on the drop ID so the order is stable between opens. After the newest drop, show the previous drop the same way.
- **Read state:** a post counts as seen once it has been at least 60% on screen for one second (IntersectionObserver). Audio counts as played at 90%. Store only IDs in `sideline.feed.v1`.
- **Top of feed:** a slim header showing the drop ("Week 8 · Monday drop"), how many posts are left, and roughly how much time remains (text posts count as 20 seconds, carousels as 10 seconds per slide, audio and video by duration).
- **Caught up:** when every post in the newest drop is seen, show a "You're caught up for Week 8" card, then a divider before the older drop.
- **Filter chips** at the top: All, Listen, Read, plus a chip per conference (SEC, Big Ten, ACC, Big 12). Listen shows audio and video only. Conference chips filter by `teams`. No search for now.
- **Team links:** team names in a post link to Sideline's existing team page, which shows my notes. On a team page, add a small "In the feed" section listing feed posts that mention that team.
- **Pull to refresh** is not needed. The feed fetches `feed/index.json` with `cache: 'no-store'` each time the tab opens.

### Audio

- One shared audio player for the whole app, so only one clip plays at a time.
- A mini player bar sits above the tab bar while something is playing: account name, title, play/pause, skip 15 seconds, and "Next" to play the next unplayed audio post in feed order.
- **Play all** button in the header plays every unplayed audio post in order, like a short podcast. This is the most important audio feature, since it's how I'll listen while doing something else.
- Use the Media Session API (title, artist = account name, artwork = account avatar, play/pause/next handlers) so lock-screen controls work where iOS allows it. Home-screen web apps on iOS can pause audio when the screen locks. Handle that gracefully: remember the position and resume from it.

---

## 6. House accounts

Ten accounts, each with a beat, a voice, and an avatar (a colored circle with initials, generated in CSS, no image files needed). Store in `accounts.json`:

| Key | Name | Beat | Edge TTS voice |
|---|---|---|---|
| `slate` | The Slate | The week's schedule by conference | en-US-AndrewMultilingualNeural |
| `rankings` | Rankings Desk | Poll movement, who rose and fell | en-US-AvaNeural |
| `stat-sheet` | Stat Sheet | ESPN team stats and side-by-side comparisons | en-US-BrianNeural |
| `matchup` | Matchup Room | Game-by-game breakdowns (carousels) | en-US-GuyNeural |
| `spotlight` | Spotlight | Player features | en-US-EmmaNeural |
| `injury` | Injury Wire | Availability and injury news | en-US-ChristopherNeural |
| `weather` | Weather Watch | Forecasts for outdoor games | en-US-JennyNeural |
| `number` | The Number | Spread and total trends, raw numbers only | en-US-EricNeural |
| `recap` | Recap | What happened last Saturday | en-US-SteffanNeural |
| `around` | Around the Sport | Coaching news and storylines | en-US-AriaNeural |

Voices are a starting point. Build a `tools/voice_samples.py` that renders the same 20-second script in each voice so I can listen and swap any I don't like.

---

## 7. Content pipeline (the `tools/` folder)

Runs on my Windows PC from the Sideline folder. Python 3. Everything mechanical is a script so Claude's usage goes only to research and writing.

The weekly flow:

1. **Research and write (Claude Code, using the weekly prompt, a separate document).** Output is `feed/<drop-id>/draft.json`: the posts with their text, plus *specs* for graphics instead of finished images (for example `{ "chart": "compare_bars", "data": {...} }`) and *scripts* for audio instead of audio files.
2. **`tools/fetch_espn.py`**: pulls the data the writing step needs from ESPN's public JSON endpoints (scoreboard, rankings, team statistics) into `feed/<drop-id>/data/`. Writing uses these numbers so stats are never typed from memory.
3. **`tools/build_graphics.py`**: turns each graphic spec into a 1080-wide PNG. Use matplotlib (or Pillow for text cards). Templates needed at launch:
   - `stat_card`: one big number plus label and context line
   - `compare_bars`: two teams side by side across 4 to 8 stats, team colors
   - `trend_table`: a small table (for ATS and over/under records)
   - `rank_movers`: poll risers and fallers
   - `slate_card`: a conference's games for the week
   - `player_card`: name, position, team, a few stat lines. Official roster headshot only if the spec includes a URL from the school's athletics site; otherwise initials.

   Team colors come from ESPN's team data (`color`, `alternateColor`). One consistent visual style for all graphics, dark background, readable on a phone.
4. **`tools/tts.py`**: renders every audio script with `edge-tts` using the account's voice. MP3, mono, 64 kbps. Writes the real duration back into the post.
5. **`tools/make_video.py`**: optional, phase 3. Stitches a carousel's slides with its audio into a 720x1280 MP4 with ffmpeg (each slide held for its share of the audio).
6. **`tools/validate.py`**: checks every post against the schema, every file path exists, every `teams` name matches ESPN, nothing over size limits, and flags banned phrases (`pick`, `lock`, `best bet`, `lean`, `projected winner`, `we like`, `hammer`, `fade`, and similar) for my review. Fails loudly instead of publishing a broken drop.
7. **`tools/publish.py`**: writes `posts.json` from the draft, updates `feed/index.json`, prunes drops older than the last 4, then `git add`, `git commit`, `git push`. GitHub Pages redeploys within a couple of minutes.

Each script runs on its own and is safe to re-run. A single `tools/run_drop.py <drop-id>` runs steps 2 through 7 in order (step 2 runs before writing too, as noted in the weekly prompt).

`requirements.txt` in `tools/`: `edge-tts`, `matplotlib`, `pillow`, `requests`. ffmpeg is a separate install, only needed for video.

---

## 8. Build order

**Phase 1: the feed reads a drop.**
Feed tab, `feed.js`, rendering for `text`, `carousel`, `xpost`, and `slate`, tier ordering, read state, filter chips, the caught-up card. Ship with a hand-made sample drop (`feed/sample/`) of about 15 posts with real-looking but clearly labeled sample content, so I can test on my phone before any real drop exists.

**Phase 2: audio.**
`audio` posts, shared player, mini player bar, Play all, Media Session. `tools/tts.py` and `tools/voice_samples.py`.

**Phase 3: pipeline.**
`fetch_espn.py`, `build_graphics.py` with the six templates, `validate.py`, `publish.py`, `run_drop.py`. Run one real Monday drop end to end.

**Phase 4: polish.**
`video` posts and `make_video.py`, the "In the feed" section on team pages, remaining time estimate.

Ship and test each phase on my phone before starting the next.

---

## 9. Done when

- The Feed tab opens the newest drop in under two seconds on my iPhone, scrolls smoothly through 120+ posts, and carousels swipe without moving the page.
- Play all plays every unplayed clip in order and remembers where it stopped.
- My existing notes, teams, and games are all still there after the update.
- A full Monday drop goes from draft to live on my phone with one command after the writing step.
- Nothing in the feed is anyone's pick or prediction.
