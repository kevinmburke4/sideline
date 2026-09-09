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

## Dictation

The Dictate button uses the browser's built-in speech recognition (Safari on iOS 14.5 or later, Chrome on desktop). Safari sometimes stops listening after a pause; the app restarts it automatically until you tap Stop. If the button is missing, the microphone key on the iOS keyboard does the same job inside the text box.
