# Sideline: Voice-First College Football Notebook

**Build spec for Claude Code.** Hand this whole file over as the starting brief.

---

## 1. What this is

A hands-free iOS app for capturing and recalling college football observations. Two modes:

**Recap mode** (Sunday/Monday): the app walks through last week's Power 4 slate one game at a time, asks whether I watched it, and if so asks what I thought. I talk, it stores what I said, it moves on. No screen touching. I should be able to do this on a walk with AirPods in.

**Preview mode** (Thursday/Friday): the app walks through the upcoming Power 4 slate one game at a time, reads back everything I've said about both teams so far this season, adds a short factual briefing pulled from an API, and lets me record a pre-game thought.

The point is that I watch a lot of games and forget what I saw. This is the memory layer. The value is entirely in getting my own observations back in front of me at the moment I need them, which is when I'm thinking about the next game.

**Non-goals:** this is not a betting tool, not a prediction engine, and it should never surface anyone else's analysis or picks. Only my notes plus neutral factual data.

---

## 2. Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Platform | Native iOS, SwiftUI, distributed via TestFlight | Only way to get real background audio and AirPods behavior |
| Minimum OS | iOS 26 | Required for `SpeechAnalyzer` / `SpeechTranscriber`, which is the only Apple API built for long-form continuous transcription |
| Voice interaction | Hands-free turn-taking with voice activity detection | Not push-to-talk, not full realtime speech-to-speech. It asks, waits for me to stop talking, moves on |
| Scope | Power 4 only (SEC, Big Ten, ACC, Big 12) plus Notre Dame | Roughly 25-30 games a week, which after the "did you watch it" filter is a 10-15 minute session |
| Preview depth | My notes plus light factual research | Records, results, key season stats. No outside analysis |
| Storage | On-device SwiftData, CloudKit private sync | No backend to run, notes stay mine |

---

## 3. Architecture

```
┌──────────────────────────────────────────────┐
│  SwiftUI app                                 │
│                                              │
│  SessionEngine (state machine)               │
│    ├── VoicePipeline                         │
│    │     ├── AVSpeechSynthesizer   (out)     │
│    │     ├── SpeechTranscriber     (in)      │
│    │     └── TurnDetector          (VAD)     │
│    ├── QueueBuilder                          │
│    └── NoteWriter                            │
│                                              │
│  Data                                        │
│    ├── SwiftData store + CloudKit            │
│    ├── CFBDClient    (schedule, results)     │
│    └── LLMClient     (structuring, summary)  │
└──────────────────────────────────────────────┘
```

No server. Both API keys are entered once in Settings and held in Keychain. If this ever gets shared with anyone else, put a Cloudflare Worker in front of the LLM call so the key is not on device, but for a personal TestFlight build that is over-engineering.

---

## 4. Data sources

### CollegeFootballData API

Base URL `https://api.collegefootballdata.com`, Bearer token auth, free key at `collegefootballdata.com/key`.

Free tier is 1,000 calls per month. Weekly usage here is maybe 6-10 calls, so free is plenty, but Tier 1 at $1/month is worth it as insurance against a bad retry loop. Exceeding the limit disables the key until the next cycle, so **cache everything in SwiftData and never call the API from inside the voice loop**.

Endpoints needed:

- `GET /games?year={y}&week={w}&seasonType=regular&division=fbs` — the slate, plus final scores once played
- `GET /teams/fbs?year={y}` — team list, conference, logos. Fetch once per season
- `GET /records?year={y}&team={t}` — season records for the preview briefing
- `GET /stats/season?year={y}&team={t}` — season stat lines
- `GET /ratings/sp?year={y}` — SP+ ratings, one call covers all teams
- `GET /rankings?year={y}&week={w}` — AP/Coaches poll for context

Sync strategy: one background refresh Sunday morning that pulls the completed week's results and next week's schedule in a handful of calls, then writes to SwiftData. Everything the voice session reads comes from local storage.

### LLM (Anthropic API)

Used for three things only, all outside the real-time loop:

1. Correcting mangled proper nouns and structuring a raw transcript into a note (extract teams, players, themes, a one-line gist)
2. Generating at most one follow-up question when an answer was very short
3. Writing the end-of-session synthesis and the preview briefings

---

## 5. Data model (SwiftData)

```swift
@Model class Team {
    var cfbdId: Int
    var school: String            // "Ohio State"
    var spokenName: String        // "Ohio State" - what TTS says and STT should expect
    var conference: String
    var logoURL: String?
    var isPriority: Bool          // my teams, ordered first in the queue
}

@Model class Game {
    var cfbdId: Int
    var season: Int
    var week: Int
    var startDate: Date
    var homeTeam: Team
    var awayTeam: Team
    var homePoints: Int?
    var awayPoints: Int?
    var completed: Bool
    var venue: String?
    var isConferenceGame: Bool
    var notes: [GameNote]
}

@Model class GameNote {
    var game: Game
    var kind: NoteKind            // .recap or .preview
    var watched: Bool?            // nil for preview notes
    var rawTranscript: String       // exactly what I said, never overwritten
    var correctedTranscript: String? // proper nouns fixed by the LLM pass
    var gist: String?               // LLM one-liner
    var mentionedTeams: [String]
    var mentionedPlayers: [String]
    var themes: [String]          // "QB play", "OL injury", "tempo", "secondary"
    var createdAt: Date
    var audioPath: String?        // optional, keep the recording
}

@Model class RecapSession {
    var season: Int
    var week: Int
    var kind: NoteKind
    var startedAt: Date
    var completedAt: Date?
    var lastGameIndex: Int        // resume point if interrupted
    var synthesis: String?        // end-of-session summary
}
```

**Rule: `rawTranscript` is sacred.** Every derived field is regenerable. If the LLM structuring is wrong I want the original words intact.

---

## 6. The voice pipeline

This is the part that will make or break the app. Build it carefully and in isolation before wiring it to anything else.

### Audio session

```swift
try session.setCategory(.playAndRecord,
                        mode: .voiceChat,
                        options: [.allowBluetoothHFP, .defaultToSpeaker])
```

`.voiceChat` mode is what turns on Apple's acoustic echo cancellation. Without it the transcriber will hear the app's own TTS and transcribe the question as my answer. This is the single most common way this kind of app fails.

Note that `.allowBluetooth` was renamed `.allowBluetoothHFP` in the iOS 26 SDK. Old sample code will show the deprecated spelling.

Add `UIBackgroundModes: [audio]` to Info.plist.

### Turn state machine

```
IDLE
  └─> SPEAKING      TTS reads the prompt. Mic is live but transcript is discarded.
        └─> LISTENING   Start capturing. Roll a silence timer.
              ├─ no speech for 6s after prompt  -> reprompt once, then skip
              ├─ speech detected, then 2.5s of silence -> END_TURN
              └─ command word detected -> handle immediately
        └─> PROCESSING  Persist transcript. Decide next state.
              ├─ yes/no answer -> branch, no LLM call
              ├─ substantive answer -> store, advance
              └─ very short/vague answer -> one LLM follow-up, then advance
        └─> next game, back to SPEAKING
```

### Turn detection

Use `SpeechTranscriber` with volatile (partial) results streaming. The turn ends when no new finalized text has arrived for 2.5 seconds AND at least one word was spoken. Back that with an energy-based check on the `AVAudioEngine` tap so a long thinking pause with background noise does not end the turn prematurely.

Make the silence threshold a setting. 2.5s is a guess; the right number is whatever stops cutting me off mid-thought.

### Proper nouns (important)

Heads up: `SpeechAnalyzer` as of iOS 26.0 exposes **no** custom vocabulary or contextual-strings biasing. The old `SFSpeechRecognizer.contextualStrings` has no equivalent. So player names, school nicknames, and coach names will come back mangled and there is no way to prevent it at the recognition layer.

The fix is a correction pass in Phase 4, not a recognition setting. Send the raw transcript to the LLM along with a context block containing both teams' names, nicknames, and rosters for that specific game, and ask it to produce a corrected transcript alongside the structured note. Store both: `rawTranscript` untouched, `correctedTranscript` as the searchable one.

This is also why the app should never depend on exact name matching for any feature.

### Three more gotchas that will otherwise cost a day each

1. **Audio format mismatch fails silently.** The mic's native format usually does not match `SpeechAnalyzer.bestAvailableAudioFormat()`. Feed a mismatched buffer and you get a clean compile and zero transcription with no error thrown. Always run tap buffers through `AVAudioConverter` first.
2. **The speech model may need downloading.** Check `SpeechTranscriber.installedLocales` on launch and use `AssetInventory.assetInstallationRequest()` if the model is missing. Handle this at app start, not at session start, or the first prompt of a walk will hang.
3. **Volatile vs finalized results.** Set `reportingOptions: [.volatileResults]` to get partials for turn detection, but only persist text where `result.isFinal` is true. Use volatiles for the silence timer and command matching, never for storage.

### Voice commands

Always active during LISTENING, matched on the partial transcript before turn-end logic:

| Say | Does |
|---|---|
| "skip" / "next" | Move to next game, discard current turn |
| "repeat" / "say that again" | Re-read the prompt |
| "go back" | Return to the previous game |
| "scratch that" | Delete the note just recorded, re-ask |
| "pause" | Halt the session, hold the resume point |
| "done" / "that's it" | End the session, go to synthesis |

Confirm each command with a short audio cue rather than a spoken sentence. Speed matters more than politeness here.

---

## 7. Recap session flow

**Queue order:** priority teams first, then by AP ranking of the higher-ranked participant, then by margin (close games are more interesting to talk about). Games I have already noted this week are excluded on resume.

```
App:  "Week 3 recap. Twenty-six Power 4 games. Let's go."

App:  "Ohio State at Texas. Ohio State won 27 to 17. Did you watch it?"
Me:   "Yeah"
App:  "What stood out?"
Me:   [talks for 40 seconds]
App:  [chime] "Got it."

App:  "Alabama at Georgia. Georgia won 24 to 21. Did you watch it?"
Me:   "No"
App:  "Alabama at Auburn..." [immediately]

...

App:  "That's everything. You had notes on eleven games. Want the recap?"
Me:   "Yeah"
App:  [reads a 60 second synthesis: recurring themes, teams I was high or low on,
       anything I flagged to watch next week]
```

Design notes:

- Score is read **before** "did you watch it" so I have the context to remember the game
- On "no", advance instantly with no acknowledgment. The dead air is what makes a long queue tolerable
- Only ask a follow-up if the answer was under about 15 words or the LLM flags it as vague. One follow-up maximum, never two
- If a note mentions a team not playing in that game, tag it to that team too. Half of what I say about a game is about somebody else's future opponent

---

## 8. Preview session flow

```
App:  "Week 4 preview. Fourteen Power 4 games worth talking about."

App:  "Ohio State at Illinois, Saturday at noon.
       Ohio State is 3 and 0, SP+ rank 2. Illinois is 2 and 1, SP+ rank 31.
       Here's what you said about Ohio State this season:
       [reads gists from prior notes, most recent first]
       And Illinois:
       [same]
       Anything on this one?"
Me:   [talks or says skip]
App:  "Noted."
```

The briefing is deliberately thin: record, SP+ rank, last result, and my own notes. No spreads, no totals, no anybody else's take. If a betting line is ever wanted it goes behind a setting that is off by default, and it shows the raw number with no commentary.

Cap the read-back at three or four note gists per team so this does not turn into a lecture. Add a "tell me more" command that reads the full note history for a team on demand.

---

## 9. Build phases

Each phase should end with something runnable on a device.

**Phase 0 — Data layer.** CFBD client, SwiftData models, weekly sync. A plain list view showing this week's Power 4 games with scores. No voice at all. Verify the data is right before building anything on top of it.

**Phase 1 — Silent recap.** The full session flow as an on-screen text interface: game card, Watched/Didn't Watch buttons, a text field for notes. This proves the queue logic, the state machine, and persistence without any audio complexity. It is also a permanent fallback for when I am somewhere I cannot talk.

**Phase 2 — Voice out.** Add `AVSpeechSynthesizer` reading the prompts. Still tapping buttons to answer. Tune the phrasing here: prompts that read fine on screen are often too wordy out loud.

**Phase 3 — Voice in.** `SpeechTranscriber`, the audio session config, turn detection, command words. This is the hard phase. Budget real time for it. Test walking outdoors with AirPods, not sitting at a desk.

**Phase 4 — Intelligence.** LLM proper-noun correction, structuring of transcripts, follow-up questions, end-of-session synthesis. Runs after the session, not during.

**Phase 5 — Preview mode.** Note retrieval by team, briefing generation, the second session type.

**Phase 6 — Polish.** Session resume, interruption handling, a browsable notes archive with search, export.

---

## 10. Known risks

- **Echo.** Covered above, but expect to spend time on it. If AEC is imperfect, gate the transcriber so it ignores everything until 200ms after TTS finishes.
- **Locked screen.** Background audio playback works with the audio background mode. Starting a *new* recording while the device is locked is unreliable. Plan for the app to be foregrounded with the screen on (in a pocket is fine) rather than promising a fully locked experience. Validate this early in Phase 3 because it changes the ergonomics.
- **Interruptions.** Phone calls, other apps grabbing audio, AirPods disconnecting. Handle `AVAudioSession.interruptionNotification` and always be able to resume at `lastGameIndex`.
- **Proper nouns.** No recognition-layer fix exists. The LLM correction pass helps but will not be perfect. Do not build features that depend on player names being transcribed exactly.
- **API budget.** Cache hard. Never call CFBD inside a session.
- **Long queues.** Twenty-six games is a lot of prompts. If sessions feel long in practice, add a pre-filter: swipe through the slate on screen for ten seconds marking which ones I watched, then only voice-prompt those.

---

## 11. Open questions to settle during the build

1. Keep the audio recordings, or transcript only? Recordings are useful for correcting bad transcription but they add storage and sync weight. Suggest keeping them for the current season only.
2. Should a note be attachable to a team rather than a game? Probably yes, as a separate "general thought" command available at any point in a session.
3. Does the synthesis get saved as a readable document, or is it audio-only? Suggest saving it as text so it is searchable later.
4. Notre Dame and other independents: worth including a small manual watchlist of non-Power-4 teams and games.

---

## 12. Starter prompt for Claude Code

> I want to build an iOS app called Sideline. The full spec is in SIDELINE_PLAN.md in this directory. Read it, then start with Phase 0 only: set up a SwiftUI project targeting iOS 26, build the SwiftData models described in section 5, write the CollegeFootballData API client described in section 4, and give me a simple list view showing the current week's Power 4 games with scores. Do not build any voice functionality yet. Ask me for the CFBD API key setup approach before you start.

---

**Sources**

- [CollegeFootballData API tiers](https://collegefootballdata.com/api-tiers)
- [CollegeFootballData getting started](https://api.collegefootballdata.com/getting-started)
- [Bring advanced speech-to-text to your app with SpeechAnalyzer (WWDC25)](https://developer.apple.com/videos/play/wwdc2025/277/)
- [SpeechAnalyzer vs SFSpeechRecognizer](https://blakecrosley.com/blog/speech-framework-vs-sfspeechrecognizer)
- [Audio Session: ensuring playback continues when screen is locked](https://developer.apple.com/library/ios/qa/qa1626/_index.html)
- [iOS 26's SpeechAnalyzer on a live mic: the 5 things the docs don't tell you](https://dev.to/simple_memo/ios-26s-speechanalyzer-on-a-live-mic-the-5-things-the-docs-dont-tell-you-2ng5)
- [AVAudioSession.CategoryOptions.allowBluetooth deprecated in Xcode 26](https://forums.swift.org/t/xcode-26-avaudiosession-categoryoptions-allowbluetooth-deprecated/80956)
