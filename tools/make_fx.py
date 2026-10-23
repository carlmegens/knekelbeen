#!/usr/bin/env python3
"""Synthesises the skull's sound effects into clips/fx_*.wav (22.05 kHz mono).

  tools/make_fx.py            # all effects
  tools/make_fx.py tiktak     # just one
  tools/make_fx.py --upload   # and put them on the skull

Files named fx_* don't move the jaw and are skipped by "Spreek" (firmware).
Everything is made from numbers, no samples, so it's free to tweak.
"""

import argparse
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RATE = 22050
rng = np.random.default_rng(31)


def t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * RATE)) / RATE


def noise(seconds: float) -> np.ndarray:
    return rng.standard_normal(int(seconds * RATE))


def onepole(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Cheap low-pass (vectorised via an exponential filter in the frequency domain)."""
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(np.fft.rfft(x) / (1 + 1j * f / cutoff), len(x))


def band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    X = np.fft.rfft(x)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def place(out: np.ndarray, sound: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * RATE)
    n = min(len(sound), len(out) - i)
    out[i:i + n] += gain * sound[:n]


def resonator(freqs, decays, gains, seconds) -> np.ndarray:
    """A struck object: a sum of decaying sines."""
    x, tt = np.zeros(int(seconds * RATE)), t(seconds)
    for f, d, g in zip(freqs, decays, gains):
        x += g * np.sin(2 * np.pi * f * tt + rng.uniform(0, 6.28)) * np.exp(-tt / d)
    return x


# ---------------------------------------------------------------- the clock

def tick(pitch: float) -> np.ndarray:
    """One escapement click: a sharp click ringing in the wooden case."""
    s = 0.12
    click = noise(s) * np.exp(-t(s) / 0.002)
    body = resonator([2400 * pitch, 3900 * pitch, 1250 * pitch, 650 * pitch],
                     [0.012, 0.008, 0.02, 0.03], [0.5, 0.3, 0.6, 0.35], s)
    return band(click, 800, 9000) * 0.6 + body


def tiktak(seconds: float = 10.0) -> np.ndarray:
    out = np.zeros(int(seconds * RATE))
    for i in range(int(seconds)):
        place(out, tick(1.0 if i % 2 == 0 else 0.82), i + rng.uniform(0, 0.006))
    return out


def gong(base: float = 165.0, seconds: float = 6.0) -> np.ndarray:
    """A clock gong: inharmonic partials, the high ones die first."""
    ratios = [0.5, 1.0, 1.19, 1.5, 2.0, 2.52, 2.98, 4.06, 5.4]
    decays = [3.5, 2.8, 2.0, 1.6, 1.3, 0.8, 0.6, 0.35, 0.2]
    gains = [0.5, 1.0, 0.5, 0.35, 0.6, 0.25, 0.2, 0.12, 0.08]
    freqs = [base * r for r in ratios]
    x = resonator(freqs, decays, gains, seconds)
    # Slight beating, like a real cast gong.
    x += resonator([f * 1.004 for f in freqs[:4]], decays[:4], [g * 0.4 for g in gains[:4]], seconds)
    strike = band(noise(0.04), 1500, 7000) * np.exp(-t(0.04) / 0.006) * 0.8
    place(x, strike, 0)
    return x * np.minimum(1, t(seconds)[::-1] / 0.3)  # fade the last bit


def klokslag() -> np.ndarray:
    return gong(seconds=6.0)


def slagen(n: int, gap: float = 2.2) -> np.ndarray:
    out = np.zeros(int(((n - 1) * gap + 6.5) * RATE))
    for i in range(n):
        place(out, gong(), i * gap)
    return out


def middernacht() -> np.ndarray:
    return slagen(12)


def tube(freq: float, seconds: float = 3.5) -> np.ndarray:
    """A chime tube: brighter, nearly harmonic overtones."""
    return resonator([freq, freq * 2.76, freq * 5.4, freq * 8.9, freq * 2.0],
                     [1.6, 0.7, 0.3, 0.15, 1.0], [1.0, 0.45, 0.2, 0.08, 0.15], seconds)


def klokkenspel() -> np.ndarray:
    """The Westminster hour chime, then three strokes."""
    hz = {"B3": 246.94, "E4": 329.63, "F#4": 369.99, "G#4": 415.30}
    phrases = [["G#4", "F#4", "E4", "B3"], ["E4", "G#4", "F#4", "B3"],
               ["E4", "F#4", "G#4", "E4"], ["G#4", "E4", "F#4", "B3"]]
    note, rest = 0.7, 0.9
    chime_end = len(phrases) * (4 * note + rest)
    out = np.zeros(int((chime_end + 2 * 2.2 + 6.5) * RATE))
    at = 0.0
    for ph in phrases:
        for i, n in enumerate(ph):
            place(out, tube(hz[n]), at, 0.9 if i < 3 else 1.0)
            at += note * (1.5 if i == 3 else 1)
        at += rest - note * 0.5
    place(out, slagen(3), at + 0.6)
    return out


# ---------------------------------------------------------------- spooky night

def donder(seconds: float = 9.0) -> np.ndarray:
    tt = t(seconds)
    rumble = onepole(onepole(noise(seconds), 140), 220)
    # Rolling: a few slow swells after the crack.
    roll = sum(np.exp(-((tt - c) / w) ** 2) * g
               for c, w, g in [(0.25, 0.4, 1.0), (1.4, 0.9, 0.7), (3.0, 1.3, 0.55), (5.2, 1.6, 0.3)])
    roll *= 1 + 0.4 * onepole(noise(seconds), 6) / 0.05
    crack = band(noise(seconds), 300, 4000) * np.exp(-np.maximum(tt - 0.05, 0) / 0.18) * (tt > 0.05)
    x = rumble / np.abs(rumble).max() * np.clip(roll, 0, None) + 0.25 * crack
    return x * np.minimum(1, (seconds - tt) / 1.5)


def wind(seconds: float = 12.0) -> np.ndarray:
    """Howling wind: noise through a slowly wandering narrow band."""
    n, hop, win = int(seconds * RATE), 1024, 4096
    src = noise(seconds + 1)
    out = np.zeros(n + win)
    centre = 450 + 250 * np.sin(2 * np.pi * t(seconds + 1)[::hop] / 4.3) \
        + 120 * np.sin(2 * np.pi * t(seconds + 1)[::hop] / 1.7 + 1)
    gust = 0.55 + 0.45 * np.sin(2 * np.pi * t(seconds + 1)[::hop] / 5.1 - 1.5) ** 2
    f = np.fft.rfftfreq(win, 1 / RATE)
    w = np.hanning(win)
    for k, i in enumerate(range(0, n, hop)):
        X = np.fft.rfft(src[i:i + win] * w)
        c = centre[k]
        shape = np.exp(-((f - c) / (c * 0.08)) ** 2) + 0.15 * np.exp(-((f - 2 * c) / (c * 0.15)) ** 2) \
            + 0.04 * np.exp(-((f - 300) / 600) ** 2)  # some broadband hiss
        out[i:i + win] += np.fft.irfft(X * shape, win) * w * gust[k]
    x = out[:n]
    tt = t(seconds)
    return x * np.minimum(1, tt / 2) * np.minimum(1, (seconds - tt) / 2)


def thump(freq: float, seconds: float = 0.25) -> np.ndarray:
    tt = t(seconds)
    f = freq * (1 + 0.6 * np.exp(-tt / 0.02))  # pitch drops as it lands
    ph = 2 * np.pi * np.cumsum(f) / RATE
    x = (np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)) * np.exp(-tt / 0.06)
    return x * np.minimum(1, tt / 0.004)


def hartslag(seconds: float = 10.0) -> np.ndarray:
    """Heartbeat that slowly speeds up (pitched for a small speaker)."""
    out = np.zeros(int(seconds * RATE))
    at, period = 0.2, 1.05
    while at < seconds - 0.6:
        place(out, thump(95), at, 1.0)
        place(out, thump(80), at + 0.28, 0.7)
        at += period
        period = max(0.55, period * 0.93)
    return out


def kraak(seconds: float = 3.2) -> np.ndarray:
    """A creaking door: stick-slip pulses whose rate wanders, through wood resonances."""
    out = np.zeros(int(seconds * RATE))
    tt = t(seconds)
    rate = 55 + 45 * np.sin(2 * np.pi * tt / 2.4) ** 2 + 25 * np.sin(2 * np.pi * tt * 1.3)
    ph = np.cumsum(rate) / RATE
    pulses = np.flatnonzero(np.diff(np.floor(ph)) > 0)
    body = resonator([420, 910, 1650, 2700], [0.012, 0.008, 0.005, 0.003], [1, 0.8, 0.5, 0.3], 0.05)
    env = np.sin(np.pi * tt / seconds) ** 0.6
    for p in pulses:
        if rng.random() < 0.92:
            place(out, body, p / RATE, env[p] * rng.uniform(0.6, 1.0))
    return out


def uil() -> np.ndarray:
    """Hoo... hoo-hoo-hooo."""
    out = np.zeros(int(3.6 * RATE))
    for at, d in [(0.0, 0.45), (0.95, 0.22), (1.3, 0.22), (1.65, 0.9)]:
        tt = t(d)
        f = 390 * (1 + 0.05 * np.sin(np.pi * tt / d)) * (1 - 0.06 * tt / d)
        ph = 2 * np.pi * np.cumsum(f) / RATE
        env = np.sin(np.pi * np.minimum(tt / 0.06, 1) / 2) * np.minimum(1, (d - tt) / (d * 0.5))
        breath = onepole(noise(d), 900) * 0.6
        place(out, (np.sin(ph) + 0.08 * np.sin(2 * ph) + breath) * env, at)
    return out


EFFECTS = {"tiktak": tiktak, "klokslag": klokslag, "middernacht": middernacht,
           "klokkenspel": klokkenspel, "donder": donder, "wind": wind,
           "hartslag": hartslag, "kraak": kraak, "uil": uil}
LOUDNESS = {"tiktak": -22}  # LUFS; the rest -16. Ticking should sit in the background.


def save(name: str, x: np.ndarray) -> Path:
    raw = ROOT / "clips" / "raw" / f"fx_{name}.float.wav"
    raw.parent.mkdir(parents=True, exist_ok=True)
    pcm = (x / (np.abs(x).max() + 1e-9) * 0.9 * 32767).astype(np.int16)
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    out = ROOT / "clips" / f"fx_{name}.wav"
    lufs = LOUDNESS.get(name, -16)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-af",
                    f"loudnorm=I={lufs}:TP=-1.5:LRA=20", "-ar", str(RATE),
                    "-sample_fmt", "s16", str(out)], check=True)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("names", nargs="*", choices=[[], *EFFECTS], help="effects to make (default all)")
    p.add_argument("--upload", action="store_true", help="upload to the skull")
    a = p.parse_args()
    made = []
    for name in a.names or EFFECTS:
        out = save(name, EFFECTS[name]())
        print(out.relative_to(ROOT))
        made.append(str(out))
    if a.upload:
        subprocess.run([str(ROOT / "tools" / "upload.sh"), *made], check=True)


if __name__ == "__main__":
    sys.exit(main())
