#!/usr/bin/env bash
# Text -> spooky skull WAV in clips/ (Dutch Piper voice by default)
# usage: tools/make_clip.sh <name> "text to say" [voice.onnx]
set -euo pipefail
cd "$(dirname "$0")/.."
name=$1; text=$2; voice=${3:-voices/nl_NL-pim-medium.onnx}
tmp=$(mktemp --suffix=.wav)
echo "$text" | .venv/bin/piper -m "$voice" --length-scale 1.15 -f "$tmp" 2>/dev/null
tools/spookify.sh "$tmp" "clips/$name.wav"
rm -f "$tmp"
echo "clips/$name.wav"
