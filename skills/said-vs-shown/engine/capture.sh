#!/bin/sh
# capture.sh <episode_dir> — capture every URL in input/brief.md with HyperFrames
# (screenshots + visible text + page.html) into ledger/capture/Sxx/.
#
#   ledger/sources.json        stable id map [{"id":"S01","url":"…"}]: existing ids never renumber,
#                              new URLs get the next id (URLs dropped from the brief keep their id)
#   ledger/selected.txt        optional, one URL substring per line (# comments allowed): matching
#                              sources are captured first, in the order of the lines
#   ledger/capture-log.jsonl   one line per source captured this run: {"id","url","secs","words","ok"}
#                              ok = words >= 50 (fewer usually means a bot wall, paywall or empty page)
#   ledger/capture/Sxx.log     HyperFrames output for that source
#
# env: SVS_MAX_SOURCES=n   capture at most n sources (after selected-first ordering)
#      SVS_RECAPTURE=1     recapture sources whose earlier capture is already ok (default: reuse)
#
# Never logs in, never clicks consent, never bypasses walls: a refused page is reported, not retried.
# Exit: 0 if at least one source is ok · 1 if the brief has no URL or every capture failed · 2 usage.
set -u

DIR=$(cd "$(dirname "$0")" && pwd)
if [ $# -ne 1 ]; then echo "usage: capture.sh <episode_dir>" >&2; exit 2; fi
EP=$1
BRIEF="$EP/input/brief.md"
L="$EP/ledger"
[ -f "$BRIEF" ] || { echo "capture.sh: no brief at $BRIEF" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "capture.sh: python3 not found on PATH" >&2; exit 2; }
command -v npx >/dev/null 2>&1 || { echo "capture.sh: npx not found on PATH (install Node.js >= 22)" >&2; exit 2; }
MAX=${SVS_MAX_SOURCES:-}
case "$MAX" in
  '') ;;
  *[!0-9]* | 0) echo "capture.sh: SVS_MAX_SOURCES must be a positive integer (got '$MAX')" >&2; exit 2 ;;
esac

HF_VER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["hyperframes"])' "$DIR/config.json") || {
  echo "capture.sh: cannot read hyperframes version from $DIR/config.json" >&2; exit 2; }

mkdir -p "$L/capture"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/svs-capture.XXXXXX") || exit 2
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT TERM

# 1. URLs in order of first appearance. Portable ERE (BSD and GNU grep): a ']' right after '[^' is
#    literal. Trailing sentence punctuation and markdown emphasis are trimmed.
grep -oE 'https?://[^] )>]+' "$BRIEF" \
  | sed -e "s/[.,;:!?*_\`\"']*\$//" \
  | awk 'length($0) > 0 && !seen[$0]++' > "$TMP/urls.txt"
if [ ! -s "$TMP/urls.txt" ]; then
  echo "capture.sh: no http(s) URL found in $BRIEF" >&2
  exit 1
fi

# 2. stable ids (ledger/sources.json) + selected-first order + optional limit -> plan.tsv
python3 - "$TMP/urls.txt" "$L/sources.json" "$L/selected.txt" "$TMP/plan.tsv" "$MAX" <<'PY' || exit 2
import json, os, re, sys

urls_p, sources_p, selected_p, plan_p, max_n = sys.argv[1:6]
with open(urls_p, encoding='utf-8') as f:
    urls = [u.strip() for u in f if u.strip()]
src = []
if os.path.exists(sources_p):
    with open(sources_p, encoding='utf-8') as f:
        src = json.load(f)
    if not isinstance(src, list) or not all(isinstance(s, dict) and 'id' in s and 'url' in s for s in src):
        sys.exit('capture.sh: ledger/sources.json must be a list of {"id","url"}')
by_url = {s['url']: s['id'] for s in src}
nums = [int(m.group(1)) for m in (re.fullmatch(r'S(\d+)', str(s['id'])) for s in src) if m]
nxt = max(nums, default=0) + 1
added = 0
for u in urls:
    if u not in by_url:
        sid = 'S%02d' % nxt
        nxt += 1
        added += 1
        src.append({'id': sid, 'url': u})
        by_url[u] = sid
tmp = sources_p + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(src, f, indent=1, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, sources_p)

sel = []
if os.path.exists(selected_p):
    with open(selected_p, encoding='utf-8') as f:
        sel = [l.strip() for l in f if l.strip() and not l.lstrip().startswith('#')]
order = []
for s in sel:
    order += [u for u in urls if s in u and u not in order]
n_sel = len(order)
order += [u for u in urls if u not in order]
if max_n:
    order = order[:int(max_n)]
with open(plan_p, 'w', encoding='utf-8') as f:
    for u in order:
        f.write('%s\t%s\n' % (by_url[u], u))
print('%d URLs in brief (%d new ids), %d selected first, capturing %d'
      % (len(urls), added, n_sel, len(order)), file=sys.stderr)
PY

# 3. capture, one source at a time. npx reads stdin, so it gets /dev/null (not the plan).
LOG="$L/capture-log.jsonl"
: > "$LOG"
TAB=$(printf '\t')
n=0; nok=0; nfail=0
while IFS="$TAB" read -r id url; do
  [ -n "$id" ] || continue
  n=$((n + 1))
  txt="$L/capture/$id/extracted/visible-text.txt"
  start=$(date +%s)
  rc=0
  if [ "${SVS_RECAPTURE:-0}" != 1 ] && [ -f "$txt" ] && [ "$(wc -w < "$txt" | tr -d ' ')" -ge 50 ]; then
    echo "[$id] reusing earlier capture of $url (SVS_RECAPTURE=1 to redo)" >&2
  else
    echo "[$id] capturing $url" >&2
    rm -f "$txt"
    (cd "$L" && npx -y "hyperframes@$HF_VER" capture "$url" -o "capture/$id" --skip-vision --skip-assets \
      --max-screenshots=6 --timeout=60000 --capture-budget=60000 --json) < /dev/null > "$L/capture/$id.log" 2>&1
    rc=$?
  fi
  secs=$(( $(date +%s) - start ))
  words=0
  if [ -f "$txt" ]; then words=$(wc -w < "$txt" | tr -d ' '); fi
  python3 -c 'import json,sys; a=sys.argv; w=int(a[4]); print(json.dumps({"id":a[1],"url":a[2],"secs":int(a[3]),"words":w,"ok":w>=50}, ensure_ascii=False))' \
    "$id" "$url" "$secs" "$words" >> "$LOG" || exit 2
  if [ "$words" -ge 50 ]; then
    nok=$((nok + 1))
    [ "$rc" -eq 0 ] || echo "[$id] warning: HyperFrames exited $rc but $words words were extracted; see $L/capture/$id.log" >&2
  else
    nfail=$((nfail + 1))
    echo "[$id] FAILED: exit $rc, $words words (bot wall, paywall, consent wall or empty page?); see $L/capture/$id.log" >&2
  fi
done < "$TMP/plan.tsv"

echo "captured $n sources: $nok ok, $nfail failed -> $LOG" >&2
if [ "$nok" -eq 0 ]; then
  echo "capture.sh: every capture failed" >&2
  exit 1
fi
exit 0
