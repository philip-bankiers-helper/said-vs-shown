#!/bin/sh
# loudfix.sh <in.mp4> <out.mp4> — two-pass EBU R128 loudness normalisation of the audio to the
# config.json target ("lufs", "true_peak"; -16 LUFS / -1.5 dBTP), video stream copied.
# Prints the measured result. Exit 1 if it lands outside target +/-1 LU, 2 on usage errors.
set -eu

DIR=$(cd "$(dirname "$0")" && pwd)
case "${1:-}" in
  -h | --help) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print (NR == 2 ? "usage: " : "") $0; next } { exit }' "$0"; exit 0 ;;
esac
if [ $# -ne 2 ]; then echo "usage: loudfix.sh <in.mp4> <out.mp4>" >&2; exit 2; fi
IN=$1
OUT=$2
[ -f "$IN" ] || { echo "loudfix.sh: no such file: $IN" >&2; exit 2; }
for t in ffmpeg python3; do
  command -v "$t" >/dev/null 2>&1 || { echo "loudfix.sh: $t not found on PATH" >&2; exit 2; }
done

cfg() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$DIR/config.json" "$1"; }
I=$(cfg lufs)
TP=$(cfg true_peak)

# pass 1: measure
M=$(ffmpeg -hide_banner -nostats -i "$IN" -af "loudnorm=I=$I:TP=$TP:LRA=11:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
FILTER=$(printf '%s' "$M" | python3 -c '
import json, sys
I, TP = sys.argv[1], sys.argv[2]
try:
    m = json.load(sys.stdin)
except ValueError:
    sys.exit("loudfix.sh: could not measure loudness (no audio stream?)")
if "inf" in m["input_i"]:
    sys.exit("loudfix.sh: input is silent")
print("loudnorm=I=%s:TP=%s:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
      % (I, TP, m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
' "$I" "$TP") || exit 1

# pass 2: apply (video copied as-is)
ffmpeg -y -hide_banner -loglevel error -i "$IN" -c:v copy -af "$FILTER" -ar 48000 -c:a aac -b:a 192k -movflags +faststart "$OUT"

# verify
ffmpeg -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 | python3 -c '
import re, sys
target = float(sys.argv[1])
err = sys.stdin.read()
summary = err[err.rfind("Summary:"):]
i = re.findall(r"\bI:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
tp = re.findall(r"\bPeak:\s*(-?[\d.]+|-inf)\s*dBFS", summary)
if not i:
    sys.exit("loudfix.sh: could not measure the result")
lufs = float(i[-1])
print("I: %.1f LUFS  true peak: %s dBFS  (target %s +/-1)" % (lufs, tp[-1] if tp else "?", target))
if abs(lufs - target) > 1.0:
    sys.exit("loudfix.sh: result is outside target +/-1 LU")
' "$I"
