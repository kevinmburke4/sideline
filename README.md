# Sideline

A personal college football notebook that runs in Safari on your iPhone. Browse the week's FBS schedule and scores, mark what you watched, and dictate notes that get filed against the teams involved. When you open a future game, everything you've said about either team this season is right there.

No accounts, no API keys, no backend. Schedule and results come from ESPN's public scoreboard feed. Notes live in your phone's browser storage and can be exported as JSON.

## Run it locally

Any static file server works. From this folder:

```bash
python -m http.server 8765
```

Then open http://localhost:8765 in a browser.

## Put it on your phone

The app has to be served over HTTPS for Safari to allow the microphone and for "Add to Home Screen" to work properly. Any static host works. Two free options:

- **GitHub Pages**: push this folder to a GitHub repository, then in the repo settings enable Pages from the main branch root. The app will be at `https://<you>.github.io/<repo>/`.
- **Netlify Drop**: drag this folder onto https://app.netlify.com/drop. You get an HTTPS URL immediately.

On the iPhone, open that URL in Safari, tap Share, then Add to Home Screen.

## Files

- `index.html`, `styles.css`, `app.js`: the whole app, no build step
- `sw.js`: service worker so the app shell opens offline
- `manifest.webmanifest`, `icons/`: home-screen install metadata
- `SIDELINE_PLAN.md`: the original spec this was scoped down from

## How data flows

- On first open the app fetches the current week from ESPN and caches it in localStorage, then quietly fetches the previous week too.
- Moving to another week fetches it once. Finished weeks are kept for three days before a refresh; live game days refresh every few minutes when you reopen the list.
- "Load full season so far" in the More tab pulls every week from 1 to now, which fills in team pages with full season results.
- Notes are stored under `sideline.v1` in localStorage. Export from the Notes or More tab produces a JSON file that Import can read back on another device.

## The Feed

The Feed tab shows "drops" of short posts: text with a graphic, swipeable carousels, audio clips with a shared player and Play all, narrated videos, X-style posts, and conference slate cards. Drops live in `feed/<drop-id>/` with a `posts.json`, and `feed/index.json` lists them newest first. The app only reads drops; it never generates content. See `FEED_PLAN.md` for the full design and `WEEKLY_PROMPT.md` for the writing brief.

Feed state (which posts were seen or played, one resume position) is stored under `sideline.feed.v1`, separate from your notes.

## Making a drop

Everything mechanical is a script in `tools/`. One-time setup on this PC:

```bash
python -m pip install --user -r tools/requirements.txt
```

ffmpeg is only needed for video posts (`winget install Gyan.FFmpeg`).

Weekly flow for drop `2026-wNN-mon` (or `-fri`):

1. `python tools/fetch_espn.py 2026-wNN-mon` pulls schedule, results, rankings, team stats, injuries and news from ESPN into `feed/2026-wNN-mon/data/`, with a readable `digest.md`.
2. Write `feed/2026-wNN-mon/draft.json` from that data, following `WEEKLY_PROMPT.md`. Graphics are specs, audio posts carry a `script`.
3. `python tools/run_drop.py 2026-wNN-mon --no-push` builds graphics (matplotlib), renders speech (edge-tts), stitches videos (ffmpeg), validates, and writes `posts.json`. Fix anything validate flags, then run it again without `--no-push` to commit, prune to the last four drops, and push. GitHub Pages redeploys in a couple of minutes.

`python tools/voice_samples.py` renders the same script in every house voice into the sample drop so they can be auditioned on the phone; voices are set in `accounts.json`.

## Dictation

The Dictate button uses the browser's built-in speech recognition (Safari on iOS 14.5 or later, Chrome on desktop). Safari sometimes stops listening after a pause; the app restarts it automatically until you tap Stop. If the button is missing, the microphone key on the iOS keyboard does the same job inside the text box.
