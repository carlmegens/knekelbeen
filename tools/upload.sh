#!/usr/bin/env bash
# Upload WAVs to the skull. Converts anything ffmpeg can read to 22.05 kHz mono 16-bit.
# usage: tools/upload.sh file1.wav [file2.mp3 ...]   (SKULL=ip to override)
set -euo pipefail
SKULL=${SKULL:-192.168.2.125}
failed=0
for f in "$@"; do
  name=$(basename "${f%.*}").wav
  tmp=$(mktemp -d)/$name
  ffmpeg -loglevel error -y -i "$f" -ac 1 -ar 22050 -sample_fmt s16 "$tmp"
  code=$(curl -s -o /dev/null -w "%{http_code}" -F "f=@$tmp;filename=$name" "http://$SKULL/upload" || echo 000)
  case $code in
    200) echo "uploaded $name" ;;
    507) echo "FAILED $name: the skull's storage is full - delete some clips first" >&2; failed=1 ;;
    415) echo "FAILED $name: not a playable WAV" >&2; failed=1 ;;
    *)   echo "FAILED $name: HTTP $code (is the skull online?)" >&2; failed=1 ;;
  esac
  rm -f "$tmp"
done
exit $failed
