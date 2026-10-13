#!/usr/bin/env bash
# Record your own voice from the laptop mic, spookify it, and upload it to the skull.
# usage: tools/record.sh <name> [pitch]    (pitch 1.0 = your own voice, default 0.85)
#        SPOOKY=0 tools/record.sh <name>   -> no voice effect
set -euo pipefail
cd "$(dirname "$0")/.."
name=$1; pitch=${2:-0.85}
raw=clips/raw/$name.wav
mkdir -p clips/raw
echo "🎙  Recording '$name' - speak now, press ENTER to stop."
pw-record --rate 48000 --channels 1 "$raw" &
pid=$!
read -r
kill -INT $pid; wait $pid 2>/dev/null || true
tools/spookify.sh "$raw" "clips/$name.wav" "$pitch"
printf "Duration: %.1fs\n" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "clips/$name.wav")"
read -rp "▶  Preview on laptop? [y/N] " a; [[ $a == y* ]] && pw-play "clips/$name.wav"
read -rp "⬆  Upload to skull and play it? [Y/n] " a
if [[ $a != n* ]]; then
  tools/upload.sh "clips/$name.wav"
  curl -s "http://${SKULL:-192.168.2.125}/play?f=$name.wav" >/dev/null
fi
