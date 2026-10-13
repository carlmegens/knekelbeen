#!/usr/bin/env python3
"""Make skull clips with Gemini TTS in Knekelbeen's designed voice.

  tools/gemini_clip.py welkom "Welkom, kleintjes..." --style "fluisterend en geheimzinnig"
  tools/gemini_clip.py lach "Ha ha ha!" --style "griezelig lachend" --upload
  tools/gemini_clip.py --batch clips/lines.txt --upload

Batch file lines:  name | text | style (style optional, '#' = comment).
Inline tags in the text work too: <short pause>, <long pause>, <sigh>.

The voice ID lives in voices/gemini_voice.json (made with Gemini Voice Design).
Output: clips/<name>.wav (22.05 kHz mono, trimmed and loudness-normalised;
add --spooky for the pitch/echo effect on top, usually not needed).
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = "gemini-3.8-flash-tts"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def synthesize(text: str, style: str, voice: str) -> bytes:
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {
        "model": MODEL,
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(), method="POST",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                 "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=120))
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode()
            if e.code != 429 or attempt == 4:
                sys.exit(f"Gemini TTS error {e.code}: {msg[:400]}")
            # Free tier: 3 requests/minute. Wait as long as the API asks.
            m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
            wait = float(m.group(1)) + 1 if m else 25
            print(f"  rate limit, waiting {wait:.0f} s...", flush=True)
            time.sleep(wait)
    audio = [c for step in resp.get("steps", []) if step.get("type") == "model_output"
             for c in step.get("content", []) if c.get("type") == "audio"]
    if not audio:
        sys.exit(f"No audio in response: {json.dumps(resp)[:400]}")
    return base64.b64decode(audio[-1]["data"])


def make_clip(name: str, text: str, style: str, voice: str, spooky: bool,
              force: bool, rate: int = 22050) -> Path:
    raw = ROOT / "clips" / "raw" / f"{name}.gemini.wav"
    raw.parent.mkdir(parents=True, exist_ok=True)
    if force or not raw.exists():  # reuse earlier synthesis (saves quota)
        raw.write_bytes(synthesize(text, style, voice))
    out = ROOT / "clips" / f"{name}.wav"
    if spooky:
        subprocess.run([str(ROOT / "tools" / "spookify.sh"), str(raw), str(out)],
                       env={**os.environ, "SPOOKY": "1"}, check=True)
    else:
        process(raw, out, rate)
    return out


# Gentle chain for Gemini voices: trim silence, light denoise (singing styles
# come with audible hiss), gate the pauses, normalise without heavy
# compression. spookify.sh's strong compressor lifted that hiss by ~14 dB.
CLEAN = ("highpass=f=90,"
         "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,"
         "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,areverse,"
         "afftdn=nr=18:nf=-42:tn=1,"
         "agate=threshold=0.012:ratio=6:attack=5:release=150,"
         "alimiter=limit=0.89,loudnorm=I=-14:TP=-1.5:LRA=11")


def process(raw: Path, out: Path, rate: int = 22050) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-af", CLEAN,
                    "-ac", "1", "-ar", str(rate), "-sample_fmt", "s16", str(out)], check=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", nargs="?")
    p.add_argument("text", nargs="?")
    p.add_argument("--style", default="", help='acting direction, e.g. "fluisterend"')
    p.add_argument("--batch", help="file with: name | text | style")
    p.add_argument("--spooky", action="store_true", help="add the pitch/echo effect")
    p.add_argument("--upload", action="store_true", help="upload to the skull")
    p.add_argument("--force", action="store_true", help="re-synthesize even if made before")
    p.add_argument("--rate", type=int, default=22050,
                   help="sample rate on the skull (16000 saves ~27%% space)")
    a = p.parse_args()

    load_env()
    voice = json.loads((ROOT / "voices" / "gemini_voice.json").read_text())["id"]
    jobs = []
    if a.batch:
        for line in Path(a.batch).read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                parts = [x.strip() for x in line.split("|")]
                jobs.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    elif a.name and a.text:
        jobs.append((a.name, a.text, a.style))
    else:
        p.error("give NAME TEXT, or --batch FILE")

    made = []
    for name, text, style in jobs:
        out = make_clip(name, text, style, voice, a.spooky, a.force, a.rate)
        print(f"{out.relative_to(ROOT)}  ({style or 'no style'})")
        made.append(str(out))
    if a.upload:
        subprocess.run([str(ROOT / "tools" / "upload.sh"), *made], check=True)


if __name__ == "__main__":
    main()
