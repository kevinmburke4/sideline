"""Shared helpers for the Sideline content pipeline. Run scripts from the Sideline folder."""
from __future__ import annotations

import asyncio
import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "feed"
ACCOUNTS = ROOT / "accounts.json"


def load_json(path: Path, default=None):
    if not Path(path).exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def accounts() -> dict:
    """House accounts only (entries with a voice). The X list lives under x_accounts()."""
    return {k: v for k, v in load_json(ACCOUNTS).items() if isinstance(v, dict) and v.get("voice")}


def x_accounts() -> list[dict]:
    """The curated X list from accounts.json (handle, name, affiliation, group, confidence, flag)."""
    return [x for x in load_json(ACCOUNTS).get("xaccounts", []) if isinstance(x, dict) and x.get("handle")]


def drop_dir(drop_id: str) -> Path:
    return FEED / drop_id


def posts_file(drop_id: str, prefer_draft: bool = True) -> Path:
    """draft.json while a drop is being built, posts.json once published."""
    d = drop_dir(drop_id)
    if prefer_draft and (d / "draft.json").exists():
        return d / "draft.json"
    return d / "posts.json"


def load_posts(path: Path) -> list:
    data = load_json(path)
    return data if isinstance(data, list) else data.get("posts", [])


def find_ffprobe() -> str | None:
    hit = shutil.which("ffprobe")
    if hit:
        return hit
    pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffprobe.exe")
    hits = glob.glob(pattern)
    return hits[0] if hits else None


def find_ffmpeg() -> str | None:
    hit = shutil.which("ffmpeg")
    if hit:
        return hit
    pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe")
    hits = glob.glob(pattern)
    return hits[0] if hits else None


def media_duration(path: Path) -> float:
    """Seconds, via ffprobe when available; otherwise a bitrate estimate for edge-tts MP3s (48 kbps)."""
    probe = find_ffprobe()
    if probe:
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            return float(out)
        except Exception:
            pass
    return os.path.getsize(path) * 8 / 48000


async def _render_async(text: str, voice: str, out: Path, rate: str = "+0%") -> None:
    import edge_tts  # imported lazily so the other scripts don't need it

    out.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out))


FEMALE_HINTS = ("Ava", "Emma", "Jenny", "Aria", "Michelle", "Ana", "Sara")


def render_sapi(text: str, voice: str, out: Path) -> float:
    """Fallback: Windows' built-in speech engine via PowerShell, then ffmpeg to mono 64 kbps MP3."""
    import tempfile
    import time

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is needed for the Windows speech fallback")
    gender = "Female" if any(h in voice for h in FEMALE_HINTS) else "Male"
    wav = Path(tempfile.gettempdir()) / f"sideline_tts_{int(time.time() * 1000)}.wav"
    txt = Path(tempfile.gettempdir()) / f"sideline_tts_{int(time.time() * 1000)}.txt"
    txt.write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::{gender}); "
        "$s.Rate = 0; "
        f"$s.SetOutputToWaveFile('{wav}'); "
        f"$s.Speak([System.IO.File]::ReadAllText('{txt}', [System.Text.Encoding]::UTF8)); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-b:a", "64k", str(out)], check=True)
    wav.unlink(missing_ok=True)
    txt.unlink(missing_ok=True)
    return media_duration(out)


def render_speech(text: str, voice: str, out: Path, rate: str = "+0%", allow_fallback: bool = True) -> float:
    """Render text to an MP3 with edge-tts (3 attempts); fall back to the Windows speech engine if the service refuses."""
    import time

    last = None
    for attempt in range(3):
        try:
            asyncio.run(_render_async(text, voice, out, rate))
            return media_duration(out)
        except Exception as e:  # 403s, timeouts, DRM clock errors
            last = e
            time.sleep(2 + attempt * 3)
    if not allow_fallback or os.environ.get("SIDELINE_NO_SAPI"):
        raise last
    print(f"    edge-tts failed ({str(last)[:60]}...); using Windows speech fallback")
    return render_sapi(text, voice, out)


def update_index_count(drop_id: str) -> None:
    idx_path = FEED / "index.json"
    idx = load_json(idx_path, {"drops": []})
    posts = load_posts(posts_file(drop_id, prefer_draft=False)) if (drop_dir(drop_id) / "posts.json").exists() else []
    for d in idx.get("drops", []):
        if d.get("id") == drop_id:
            d["posts"] = len(posts)
    save_json(idx_path, idx)
