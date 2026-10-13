#!/bin/sh
# setup.sh — install what the Said vs. Shown engine needs. Idempotent; macOS and Linux
# (Windows: run it under WSL or Git Bash).
#
# usage: setup.sh [--dry-run] [--no-skills] [--with-parakeet] [--no-telemetry]
#
#   --dry-run         print every step, its command and its disk use; change nothing
#   --no-skills       leave the user's global agent skill folders alone: skip the HyperFrames agent
#                     skills install. Agents then read HyperFrames docs through the pinned CLI
#                     (npx -y hyperframes@<config.json version> docs <topic>); doctor reports WARN, not FAIL
#   --with-parakeet   also install the Parakeet ASR model (~640 MB). Without it, transcription
#                     uses Whisper small.en, which HyperFrames fetches on first use (~470 MB)
#   --no-telemetry    run `npx -y hyperframes@<config.json version> telemetry disable` (a global
#                     HyperFrames setting). Without it the telemetry status is printed and left alone
#
# Everything except the HyperFrames agent skills goes under $SVS_HOME (default: "home" in config.json,
# ~/.said-vs-shown). Keep that path short: espeak (inside Kokoro) breaks on data paths over ~160 characters.
#   $SVS_HOME/node     puppeteer-core + @puppeteer/browsers, pinned in engine/package.json
#   $SVS_HOME/kokoro   Python 3.12 venv with kokoro-onnx + soundfile (skipped if $HYPERFRAMES_PYTHON already has them)
#   $SVS_HOME/chrome   chrome-headless-shell, only when no usable Chrome exists
# Through npx hyperframes@<config.json version>: `skills update` (unless --no-skills), which installs or
# overwrites the HyperFrames agent skills (latest from GitHub) in ~/.claude/skills and ~/.agents/skills and links
# them into the skill folders of other agents it finds (~/.cursor, ~/.gemini, ~/.config/opencode,
# ~/.codeium/windsurf); and the optional steps above. Without a terminal its output goes to
# $SVS_HOME/skills-update.log.
# Next step afterwards: node <this folder>/doctor.mjs
set -eu

DIR=$(cd "$(dirname "$0")" && pwd)
DRY=0
PARAKEET=0
NOTEL=0
SKILLS=1
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --no-skills) SKILLS=0 ;;
    --with-parakeet) PARAKEET=1 ;;
    --no-telemetry) NOTEL=1 ;;
    -h | --help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
    *) echo "setup.sh: unknown option $a (try --help)" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
run() {
  if [ "$DRY" = 1 ]; then say "   [dry-run] $*"; else say "   \$ $*"; "$@"; fi
}
step() { say ""; say "==> $*"; }

# --- 0. prerequisites -------------------------------------------------------------------------
step "0/6 prerequisites"
case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin) PKG="brew install" ;;
  Linux) PKG="sudo apt install (or your distro's package manager)" ;;
  *) PKG="your package manager" ;;
esac
missing=0
if command -v node >/dev/null 2>&1 && [ "$(node -p 'const [a,b]=process.versions.node.split(".").map(Number); +(a>22||(a===22&&b>=12))')" = 1 ]; then
  say "   ok       node $(node -p 'process.versions.node')"
else
  say "   MISSING  node >= 22.12 — install from https://nodejs.org or: $PKG node"; missing=1
fi
for t in ffmpeg ffprobe; do
  if command -v "$t" >/dev/null 2>&1; then say "   ok       $t"; else say "   MISSING  $t — $PKG ffmpeg"; missing=1; fi
done
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  say "   ok       python3 $(python3 -c 'import platform; print(platform.python_version())')"
else
  say "   MISSING  python3 >= 3.9 — $PKG python3"; missing=1
fi
if command -v uv >/dev/null 2>&1; then
  say "   ok       uv $(uv --version 2>/dev/null | awk '{print $2}')"
else
  say "   MISSING  uv — $PKG uv, or see https://docs.astral.sh/uv/getting-started/installation/"; missing=1
fi
if [ "$missing" = 1 ]; then
  say ""; say "Install the missing tools above, then re-run setup.sh."
  exit 1
fi

HF_VER=$(node -p 'require(process.argv[1]).hyperframes' "$DIR/config.json")
HOME_CFG=$(node -p 'require(process.argv[1]).home' "$DIR/config.json")
PUP_VER=$(node -p 'require(process.argv[1]).dependencies["puppeteer-core"]' "$DIR/package.json")
BRO_VER=$(node -p 'require(process.argv[1]).dependencies["@puppeteer/browsers"]' "$DIR/package.json")
SVS_HOME=${SVS_HOME:-$HOME_CFG}
case "$SVS_HOME" in "~") SVS_HOME=$HOME ;; "~/"*) SVS_HOME="$HOME/${SVS_HOME#\~/}" ;; esac
export SVS_HOME
HF="hyperframes@$HF_VER"
NODE_DIR="$SVS_HOME/node"
KOKORO="$SVS_HOME/kokoro"

say ""
say "SVS_HOME = $SVS_HOME   (override with SVS_HOME=...)"
say "HyperFrames $HF_VER · puppeteer-core $PUP_VER · @puppeteer/browsers $BRO_VER"
say "Disk, worst case on a fresh machine:"
say "   ~35 MB   $NODE_DIR (puppeteer-core, @puppeteer/browsers)"
say "  ~150 MB   $KOKORO (Python 3.12 venv; uv may also fetch a Python 3.12 build, ~40 MB)"
say "  ~340 MB   Kokoro model + voices, fetched by HyperFrames into ~/.cache/hyperframes on the first TTS"
say "  ~120 MB   HyperFrames CLI in the npm/npx cache (+ ~390 MB of its own Chrome on the first capture/render)"
say "  ~200 MB   $SVS_HOME/chrome, only if no usable Chrome is found"
if [ "$SKILLS" = 1 ]; then
  say "   ~11 MB   HyperFrames agent skills (latest from GitHub) -> ~/.claude/skills and ~/.agents/skills, linked into"
  say "            ~/.cursor, ~/.gemini, ~/.config/opencode, ~/.codeium/windsurf skill folders when those agents exist"
else
  say "     0 MB   HyperFrames agent skills: not installed (--no-skills); global agent skill folders are left alone"
fi
if [ "$PARAKEET" = 1 ]; then
  say "  ~640 MB   Parakeet ASR model (--with-parakeet), in ~/.cache/hyperframes"
else
  say "  ~470 MB   Whisper small.en, fetched by HyperFrames on the first transcription (or --with-parakeet: ~640 MB)"
fi
[ "$DRY" = 1 ] && say "(dry run: nothing will be changed)"

# --- 1. node deps -----------------------------------------------------------------------------
step "1/6 puppeteer-core + @puppeteer/browsers -> $NODE_DIR"
have=$(node -e '
const fs = require("fs"), path = require("path");
const v = n => { try { return JSON.parse(fs.readFileSync(path.join(process.argv[1], "node_modules", n, "package.json"), "utf8")).version } catch { return "" } };
console.log(v("puppeteer-core") === process.argv[2] && v("@puppeteer/browsers") === process.argv[3] ? "ok" : "no")
' "$NODE_DIR" "$PUP_VER" "$BRO_VER")
if [ "$have" = ok ]; then
  say "   already installed"
else
  run mkdir -p "$NODE_DIR"
  run npm install --prefix "$NODE_DIR" --save-exact --no-audit --no-fund "puppeteer-core@$PUP_VER" "@puppeteer/browsers@$BRO_VER"
fi

# --- 2. Kokoro venv ---------------------------------------------------------------------------
step "2/6 Kokoro TTS venv -> $KOKORO"
kpy() { if [ -x "$KOKORO/Scripts/python.exe" ]; then echo "$KOKORO/Scripts/python.exe"; else echo "$KOKORO/bin/python"; fi; }
if [ -n "${HYPERFRAMES_PYTHON:-}" ] && "$HYPERFRAMES_PYTHON" -c 'import kokoro_onnx, soundfile' >/dev/null 2>&1; then
  say "   HYPERFRAMES_PYTHON ($HYPERFRAMES_PYTHON) already has kokoro-onnx + soundfile: skipping the venv"
elif [ -x "$(kpy)" ] && "$(kpy)" -c 'import kokoro_onnx, soundfile' >/dev/null 2>&1; then
  say "   already installed ($(kpy))"
else
  ESPEAK="$KOKORO/lib/python3.12/site-packages/espeakng_loader/espeak-ng-data/phontab"
  if [ "${#ESPEAK}" -gt 160 ]; then
    say "   SVS_HOME is too long for espeak (${#ESPEAK} > 160 chars in its data path). Use a shorter SVS_HOME."
    [ "$DRY" = 1 ] || exit 1
  fi
  [ -x "$(kpy)" ] || run uv venv --python 3.12 "$KOKORO"
  run uv pip install --python "$(kpy)" kokoro-onnx soundfile
fi

# --- 3. HyperFrames skills --------------------------------------------------------------------
if [ "$SKILLS" = 0 ]; then
  step "3/6 HyperFrames agent skills"
  say "   skipped (--no-skills): your global agent skill folders are unchanged. Agents read HyperFrames docs with"
  say "   npx -y $HF docs <topic>   (topics: compositions, data-attributes, gsap, rendering, examples, troubleshooting)"
elif [ -t 1 ] || [ "$DRY" = 1 ]; then
  step "3/6 HyperFrames agent skills (npx -y $HF skills update)"
  run npx -y "$HF" skills update < /dev/null
else
  step "3/6 HyperFrames agent skills (npx -y $HF skills update)"
  # no terminal (e.g. an agent ran this): keep the CLI's spinner frames out of the output
  LOG="$SVS_HOME/skills-update.log"
  mkdir -p "$SVS_HOME"
  say "   \$ npx -y $HF skills update   (output: $LOG)"
  ESC=$(printf '\033')
  if npx -y "$HF" skills update < /dev/null > "$LOG" 2>&1; then
    sed "s/$ESC\[[0-9;]*[A-Za-z]//g" "$LOG" | grep -E 'Installed|updated|Linked|up to date' | tail -n 3 | sed 's/^/   /' || true
  else
    sed "s/$ESC\[[0-9;]*[A-Za-z]//g" "$LOG" | tail -n 20
    exit 1
  fi
fi

# --- 4. ASR model -----------------------------------------------------------------------------
step "4/6 speech recognition"
if [ "$PARAKEET" = 1 ]; then
  run npx -y "$HF" models install parakeet < /dev/null
else
  say "   skipped (pass --with-parakeet to install Parakeet; Whisper small.en is the fallback)"
fi

# --- 5. Chrome for receipts -------------------------------------------------------------------
step "5/6 Chrome for receipt.mjs"
if CHROME=$(node "$DIR/receipt.mjs" --find-chrome 2>/dev/null); then
  if [ "$DRY" = 1 ]; then say "   would use $CHROME (the final choice is made after step 1 installs puppeteer)"; else say "   using $CHROME"; fi
else
  BUILD=$(node -e '
try { console.log(require("module").createRequire(process.argv[1])("puppeteer-core").PUPPETEER_REVISIONS["chrome-headless-shell"]) }
catch { console.log("stable") }' "$NODE_DIR/package.json")
  run node "$NODE_DIR/node_modules/@puppeteer/browsers/lib/main-cli.js" install "chrome-headless-shell@$BUILD" --path "$SVS_HOME/chrome"
fi

# --- 6. telemetry -----------------------------------------------------------------------------
step "6/6 HyperFrames telemetry"
if [ "$NOTEL" = 1 ]; then
  run npx -y "$HF" telemetry disable < /dev/null
fi
if [ "$DRY" = 1 ]; then
  say "   [dry-run] npx -y $HF telemetry status"
else
  npx -y "$HF" telemetry status < /dev/null 2>&1 | sed -n "s/^ *\(Status:.*\)/   \1/p"
fi
if [ "$NOTEL" != 1 ]; then
  say "   left unchanged. To opt out: npx -y $HF telemetry disable (or set HYPERFRAMES_NO_TELEMETRY=1 / DO_NOT_TRACK=1)"
fi

say ""
if [ "$DRY" = 1 ]; then say "Dry run complete."; else say "Setup complete. Next: node $DIR/doctor.mjs"; fi
