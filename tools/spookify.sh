#!/usr/bin/env bash
# Any audio -> skull-ready WAV (22.05 kHz mono 16-bit), with the spooky voice filter.
# usage: tools/spookify.sh in.wav out.wav [pitch]   (pitch: 1.0 = unchanged, default 0.85)
#        SPOOKY=0 tools/spookify.sh in.wav out.wav  -> no voice effect, just clean/loud
set -euo pipefail
in=$1; out=$2; pitch=${3:-0.85}
# Trim leading/trailing silence, then (optionally) pitch down + echo, then compress + normalise.
trim="silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,areverse"
loud="acompressor=threshold=0.1:ratio=6:attack=5:release=80:makeup=2,loudnorm=I=-10:TP=-1"
if [ "${SPOOKY:-1}" = 1 ]; then
  fx="aresample=22050,asetrate=22050*$pitch,aresample=22050,atempo=$(python3 -c "print(min(2,max(0.5,1/$pitch*0.94)))"),aecho=0.8:0.6:60:0.3"
else
  fx="aresample=22050"
fi
ffmpeg -loglevel error -y -i "$in" -af "highpass=f=90,$trim,$fx,$loud" -ac 1 -ar 22050 -sample_fmt s16 "$out"
