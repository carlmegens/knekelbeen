#!/usr/bin/env python3
"""Light cues for the clips: candles and eyes play along with the samples.

  tools/make_cues.py                 # find cues for new clips -> clips/cues.txt
  tools/make_cues.py --redo lach     # find them again for these clips
  tools/make_cues.py --upload        # put the cues in the WAVs and upload them
  tools/make_cues.py --upload lach   # only these clips

clips/cues.txt has one line per clip, e.g.

  schrik       | 0.1 kaarsen_op, 0.3 ogen_flits
  fx_donder    | 0.8 ogen_flits, 0.8 kaarsen_op, 4.2 ogen_flits

and can be edited by hand (an empty line after | = no effects). Effects:
kaarsen_op, kaarsen_uit, spookgroen, ogen_flits, bliksem, donder, rook,
veel_rook, snoep - the same as the AI's.

Spoken clips get cues on the AI's trigger words ("boe", "geest", "donker",
"mijn ogen"...), found with Whisper word timestamps, plus a few extras per
clip below. Sound effects get cues on their loud hits (thunder, the clock
strikes, the heartbeat). The firmware reads them from a "fxcu" chunk in the
WAV, so they work from every soundboard, without the laptop.
"""

import argparse
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "clips"
CUES = CLIPS / "cues.txt"
SKULL = "192.168.2.125"
sys.path.insert(0, str(ROOT / "brain"))

EFFECTS = ("kaarsen_op", "kaarsen_uit", "spookgroen", "ogen_flits", "bliksem", "donder", "rook", "veel_rook", "snoep")
# How long each effect runs on the skull; a cue inside that is dropped.
LASTS = {"kaarsen_op": 1.5, "kaarsen_uit": 6.0, "spookgroen": 6.0, "ogen_flits": 0.4,
         "bliksem": 0.4, "donder": 3.0, "rook": 5.0, "veel_rook": 5.0, "snoep": 10.0}
CANDLES = {"kaarsen_op", "kaarsen_uit", "spookgroen"}  # one candle effect at a time

# Extra trigger words for the clips (on top of the AI's), word -> effect.
EXTRA_WORDS = [
    (r"^mwoe|^hahaha|^mwoehaha", "kaarsen_op"),
    (r"^rammel", "ogen_flits"),
    (r"^maan", "spookgroen"),
    (r"^altijd|^áltijd", "spookgroen"),
    (r"^spooktijd", "spookgroen"),
    (r"^tik", "ogen_flits"),
]
# Per spoken clip (see lines.txt): word start -> effect. Loose prefixes,
# because Whisper mishears the spooky voice ("Boe!" -> "boom!").
CLIP_WORDS = {
    "welkom": [(r"^dichterb", "ogen_flits"), (r"^meer", "spookgroen")],
    "snoep": [(r"^gaten", "ogen_flits")],
    "kostuum": [(r"^dood", "kaarsen_op"), (r"^al\b", "spookgroen")],
    "klok": [(r"^wegtik|^tijd", "kaarsen_uit")],
    "honderd": [(r"^opgeslot", "spookgroen"), (r"^snoep", "ogen_flits")],
    "durf": [(r"^bang", "kaarsen_op"), (r"^jij", "ogen_flits")],
    "dag": [(r"^monster", "ogen_flits"), (r"^huizen", "kaarsen_op")],
    "psst": [(r"^jij", "ogen_flits"), (r"^geheim", "spookgroen")],
    "groepje": [(r"^monster", "kaarsen_op")],
    "nogeen": [(r"^zag", "ogen_flits"), (r"^alles|^álles", "spookgroen")],
    "kietel": [(r"^kietel", "kaarsen_op")],
    "hoofdpijn": [(r"^hoofd\b|^hoofd\.", "ogen_flits")],
    "koud": [(r"^brr", "kaarsen_uit"), (r"^kippenvel", "ogen_flits")],
    "spinnen": [(r"^henk", "ogen_flits"), (r"^neus", "spookgroen")],
    "niemand": [(r"^stil", "kaarsen_uit")],
    "schrik": [(r"^bo", "kaarsen_op"), (r"^bo", "ogen_flits")],
    "tanden": [(r"^tanden", "ogen_flits"), (r"^eeuw", "kaarsen_op")],
    "dapper": [(r"^gillend|^rennen", "kaarsen_op")],
    "ouders": [(r"^snoep", "ogen_flits"), (r"^durf", "spookgroen")],
    "gaap": [(r"^sp\w*tijd", "spookgroen"), (r"^wakker", "kaarsen_op")],
    "buik": [(r"^buikpijn", "ogen_flits"), (r"^buik\b|^buik\.", "kaarsen_uit")],
    "botlied": [(r"^schedel", "kaarsen_uit"), (r"^mwoe|^haha", "kaarsen_op")],
    "liedje": [(r"^boe|^spook|^geest", "spookgroen")],
}
# Sound effects: which effects go on the loud hits, and how many hits at most.
FX = {
    "fx_donder": (["bliksem"], 6),  # a strike on every clap, so it rolls with the sound
    "fx_klokslag": (["ogen_flits"], 12),
    "fx_middernacht": (["ogen_flits"], 12),
    "fx_hartslag": (["ogen_flits"], 20),
    "fx_uil": (["ogen_flits"], 4),
    "fx_kraak": (["spookgroen"], 1),
    "fx_wind": (["kaarsen_uit"], 1),
    "fx_klokkenspel": (["spookgroen"], 1),
    "tikkendeklok": (["ogen_flits"], 20),
}
SKIP = re.compile(r"^(naam_|orgel$|fx_tiktak|fx_toontest|stem_|test_|opname|liedje_16k|denk_)")


def load(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(1)
        return x / 32768, w.getframerate()


def hits(x: np.ndarray, rate: int, most: int) -> list[float]:
    """Times (s) of the loudest sudden onsets, at least 0.35 s apart."""
    win = rate // 100
    env = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, mode="same"))[::win]  # 10 ms
    rise = np.maximum(np.diff(env, prepend=0), 0)
    slow = np.convolve(env, np.ones(30) / 30, mode="same")
    score = rise * (env > slow * 1.3) * (env > env.max() * 0.25)
    out: list[float] = []
    for i in np.argsort(score)[::-1]:
        if score[i] <= 0 or len(out) == most:
            break
        if all(abs(i / 100 - t) > 0.35 for t in out):
            out.append(i / 100)
    return sorted(out)


_whisper = None


def words(path: Path) -> list[tuple[float, str]]:
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    segs, _ = _whisper.transcribe(np.frombuffer(pcm, np.float32), language="nl", word_timestamps=True)
    return [(w.start, w.word.strip().lower()) for s in segs for w in s.words]


def tidy(cues: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """Sorted, and nothing that starts while the same kind is still running."""
    out, busy = [], {}
    for t, fx in sorted(cues):
        key = "candles" if fx in CANDLES else fx
        if t < busy.get(key, -1):
            continue
        busy[key] = t + LASTS[fx]
        out.append((round(t, 2), fx))
    return out


def find(path: Path) -> list[tuple[float, str]]:
    name = path.stem
    if name in FX:
        effects, most = FX[name]
        x, rate = load(path)
        times = hits(x, rate, most) if most > 1 else [0.1]
        return tidy([(t, fx) for t in times for fx in effects])
    import gemini  # the AI's trigger words, so clips and AI behave alike
    rules = [(re.compile(rx, re.I), fx) for rx, fx in CLIP_WORDS.get(name, [])]
    rules += [(rx, fx) for rx, fx in gemini.KEYWORD_EFFECTS]
    rules += [(re.compile(rx, re.I), fx) for rx, fx in EXTRA_WORDS]
    found = []
    for t, w in words(path):
        w = w.strip(".,!?…'\"")
        found += [(max(t, 0.0), fx) for rx, fx in rules if rx.search(w)]
    return tidy(found)


def read_cues() -> dict[str, list[tuple[float, str]]]:
    out = {}
    if CUES.exists():
        for line in CUES.read_text().splitlines():
            if not line.strip() or line.startswith("#") or "|" not in line:
                continue
            name, _, rest = line.partition("|")
            items = [c.split() for c in rest.split(",") if c.strip()]
            out[name.strip()] = [(float(t), fx) for t, fx in items if fx in EFFECTS]
    return out


def write_cues(cues: dict[str, list[tuple[float, str]]]) -> None:
    head = ("# name | seconds effect, ...  (kaarsen_op, kaarsen_uit, spookgroen, ogen_flits, bliksem, donder, rook, veel_rook, snoep)\n"
            "# Made by tools/make_cues.py; edit freely, then: tools/make_cues.py --upload\n")
    width = max(map(len, cues), default=8)
    body = "".join(f"{n:<{width}} | {', '.join(f'{t:g} {fx}' for t, fx in c)}\n"
                   for n, c in sorted(cues.items()))
    CUES.write_text(head + body)


def with_cues(path: Path, cues: list[tuple[float, str]]) -> bytes:
    """The clip as 22.05 kHz mono WAV with a fxcu chunk before the audio."""
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1",
                          "-ar", "22050", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    text = "".join(f"{int(t * 1000)} {fx}\n" for t, fx in cues).encode()
    if len(text) & 1:
        text += b"\n"
    fmt = struct.pack("<HHIIHH", 1, 1, 22050, 44100, 2, 16)
    chunks = (b"fmt " + struct.pack("<I", 16) + fmt
              + b"fxcu" + struct.pack("<I", len(text)) + text
              + b"data" + struct.pack("<I", len(pcm)) + pcm)
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def upload(name: str, data: bytes) -> bool:
    import urllib.request
    boundary = "knekelbeencues"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"f\"; filename=\"{name}.wav\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"http://{SKULL}/upload", data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        return urllib.request.urlopen(req, timeout=60).status == 200
    except OSError as e:
        print(f"  {name}: {e}")
        return False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("names", nargs="*", help="clip names (default: all)")
    p.add_argument("--redo", action="store_true", help="find the cues again, even if listed")
    p.add_argument("--upload", action="store_true", help="embed the cues and upload to the skull")
    a = p.parse_args()

    wavs = {f.stem: f for f in sorted(CLIPS.glob("*.wav")) if not SKIP.match(f.stem)}
    names = a.names or list(wavs)
    if missing := [n for n in names if n not in wavs]:
        sys.exit(f"Onbekende clip: {', '.join(missing)}")
    cues = read_cues()
    for n in names:
        if n in cues and not a.redo:
            continue
        cues[n] = find(wavs[n])
        print(f"{n:<16} {', '.join(f'{t:g} {fx}' for t, fx in cues[n]) or '-'}", flush=True)
    write_cues(cues)
    if a.upload:
        ok = sum(upload(n, with_cues(wavs[n], cues[n])) for n in names if cues.get(n))
        print(f"{ok} clips met effecten geüpload")


if __name__ == "__main__":
    main()
