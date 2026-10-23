#!/usr/bin/env python3
"""Test the skull's own microphone (INMP441 in the clock).

  tools/mic_test.py            # 4 s quiet, then 6 s talking: noise, SNR, glitches
  tools/mic_test.py --quiet 8  # only measure the noise floor / interference

Records the mic stream straight from the skull (the AI must be off, or use
the laptop mic), checks for lost packets, clicks and bit errors (wiring), hum
and whine (servo, amplifier), and saves the recording to clips/raw/mic_test.wav
so you can listen to it.
"""

import argparse
import json
import socket
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SKULL = "192.168.2.125"
PORT = 4212  # firmware MIC_CTRL_PORT
RATE = 16000


def record(seconds: float, prompt_at: float | None = None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    s.connect((SKULL, PORT))
    chunks, seqs, start, last_sub, prompted = [], [], time.monotonic(), 0.0, False
    while (now := time.monotonic()) - start < seconds:
        if now - last_sub > 2:  # the skull streams for 5 s per request
            s.send(b"MIC1")
            last_sub = now
        if prompt_at is not None and not prompted and now - start >= prompt_at:
            print(">>> Praat nu, op ongeveer een meter afstand, gewoon zoals een kind aan de deur...", flush=True)
            prompted = True
        try:
            data = s.recv(4096)
        except TimeoutError:
            continue
        if data[:2] == b"SM" and len(data) > 4:
            seqs.append(data[2] | data[3] << 8)
            chunks.append(np.frombuffer(data[4:], np.int16))
    s.close()
    return chunks, seqs


def db(x) -> float:
    return 20 * np.log10(np.sqrt(np.mean(np.square(x.astype(np.float64)))) / 32768 + 1e-9)


def analyse(x: np.ndarray, label: str) -> float:
    win = RATE // 10
    levels = [db(x[i:i + win]) for i in range(0, len(x) - win, win)]
    print(f"  {label}: gemiddeld {db(x):6.1f} dBFS, rustigste 100 ms {min(levels):6.1f}, "
          f"luidste {max(levels):6.1f}, piek {20 * np.log10(np.abs(x).max() / 32768 + 1e-9):6.1f} dBFS")
    return db(x)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quiet", type=float, help="only record this many seconds of quiet")
    a = p.parse_args()

    try:
        st = json.load(urllib.request.urlopen(f"http://{SKULL}/mic", timeout=3))
        print(f"Schedel: gain {st['gain']}, kanaal {st['slot']}, ruwe piek {st['peak']}")
    except Exception as e:
        sys.exit(f"Schedel niet bereikbaar: {e}")

    quiet_s = a.quiet or 4.0
    total = quiet_s + (0 if a.quiet else 6.0)
    print(f"Opnemen ({total:.0f} s). Eerst {quiet_s:.0f} s stil zijn...", flush=True)
    chunks, seqs = record(total, None if a.quiet else quiet_s)
    if not chunks:
        sys.exit("Geen geluid ontvangen. Staat de AI aan met de klokmicrofoon? Zet die eerst uit.")
    x = np.concatenate(chunks)

    out = ROOT / "clips" / "raw" / "mic_test.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())

    print("\nVerbinding")
    gaps = np.diff(np.array(seqs, np.int64)) % 65536
    lost = int(np.sum(gaps[gaps > 1] - 1))
    print(f"  {len(seqs)} pakketjes, {lost} kwijt ({100 * lost / max(1, len(seqs) + lost):.1f}%), "
          f"{len(x) / RATE:.1f} s audio")

    print("\nNiveau")
    split = int(quiet_s * RATE) if not a.quiet else len(x)
    noise = analyse(x[:split], "stil   ")
    if not a.quiet:
        analyse(x[split:], "praten ")
        # Only the 100 ms windows where someone actually talks, not the pauses.
        win = RATE // 10
        quiet = np.median([db(x[i:i + win]) for i in range(0, split - win, win)])
        talk = np.array([db(x[i:i + win]) for i in range(split, len(x) - win, win)])
        talk = talk[talk > quiet + 6]
        if not len(talk):
            print("  geen spraak gehoord")
            return
        speech = 10 * np.log10(np.mean(10 ** (talk / 10)))
        snr = speech - quiet
        print(f"  spraak (zonder pauzes): {speech:6.1f} dBFS")
        verdict = ("prima" if snr > 25 else "goed genoeg" if snr > 15 else
                   "te weinig: dichterbij, of het gat/de afdichting nakijken")
        print(f"  verschil spraak - ruis: {snr:.0f} dB ({verdict})")

    print("\nStoringen")
    q = x[:split].astype(np.float64)
    d = np.abs(np.diff(q))
    clicks = int(np.sum(d > max(8 * np.std(q), 2000)))
    clipped = int(np.sum(np.abs(x) >= 32767))
    zeros = 0
    run = 0
    for v in x:  # runs of exact zeros = dropped samples (or the skull talking)
        run = run + 1 if v == 0 else 0
        zeros += run == 32
    print(f"  tikjes/sprongen in de stilte: {clicks}" + ("  (goed)" if clicks == 0 else "  <- bedrading of storing"))
    print(f"  oversturing: {clipped} samples" + ("" if clipped == 0 else "  <- gain lager"))
    print(f"  gaten (stilte van precies 0): {zeros}")

    spec = np.abs(np.fft.rfft(q * np.hanning(len(q)))) + 1e-9
    f = np.fft.rfftfreq(len(q), 1 / RATE)
    smooth = np.convolve(spec, np.ones(200) / 200, mode="same")
    ratio = 20 * np.log10(spec / smooth)
    tones = []
    for i in np.argsort(ratio)[::-1]:
        if f[i] < 60 or ratio[i] < 18:
            break
        if all(abs(f[i] - t) > 15 for t, _ in tones):
            tones.append((f[i], ratio[i]))
        if len(tones) == 5:
            break
    if tones:
        print("  tonen in de stilte (brom/fluit): " + ", ".join(f"{t:.0f} Hz (+{r:.0f} dB)" for t, r in tones))
    else:
        print("  geen brom of fluittonen")
    print(f"\nOpname: {out.relative_to(ROOT)}  (beluisteren: aplay {out.relative_to(ROOT)})")


if __name__ == "__main__":
    main()
