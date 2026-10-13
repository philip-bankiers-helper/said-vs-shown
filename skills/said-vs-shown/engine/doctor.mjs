#!/usr/bin/env node
// doctor.mjs — check everything setup.sh installs, print PASS / WARN / FAIL with a one-line fix,
// then make a ~1 second Kokoro TTS smoke test. Exit 1 on any FAIL (WARN never fails).
//
// usage: node doctor.mjs [--no-smoke]
// Respects $SVS_HOME, $HYPERFRAMES_PYTHON and $CHROME_PATH exactly like the engine does.
// Read-only apart from the smoke-test WAV, which goes to a temp folder and is removed.

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log('usage: node doctor.mjs [--no-smoke]\n  Checks what setup.sh installs (PASS / WARN / FAIL, each with a fix), then a ~1 s Kokoro TTS smoke test.\n  --no-smoke  skip the smoke test. Exit 1 on any FAIL.')
  process.exit(0)
}

const ENGINE = path.dirname(fileURLToPath(import.meta.url))
// fix hints carry the absolute path, so they work from any working directory
const SETUP = `sh "${path.join(ENGINE, 'setup.sh')}"`
const CONFIG = JSON.parse(fs.readFileSync(path.join(ENGINE, 'config.json'), 'utf8'))
const PKG = JSON.parse(fs.readFileSync(path.join(ENGINE, 'package.json'), 'utf8'))
const expandHome = p => (p === '~' || p.startsWith('~/') || p.startsWith('~\\') ? path.join(os.homedir(), p.slice(1)) : p)
const SVS_HOME = path.resolve(expandHome(process.env.SVS_HOME || CONFIG.home))
const HF = `hyperframes@${CONFIG.hyperframes}`
const WIN = process.platform === 'win32'
const SMOKE = !process.argv.includes('--no-smoke')

const rows = []
function report(status, name, detail = '', fix = '') {
  rows.push(status)
  const pad = s => s.padEnd(5)
  console.log(`${pad(status)} ${name}${detail ? ` — ${detail}` : ''}`)
  if (fix && status !== 'PASS') console.log(`      fix: ${fix}`)
}

function sh(cmd, args, opts = {}) {
  // Windows: npx/npm are .cmd shims, which need a shell (and quoted args)
  const viaShell = WIN && /^(npx|npm)$/.test(cmd)
  if (viaShell) args = args.map(a => (/[\s"&|<>^]/.test(a) ? `"${a.replace(/"/g, '""')}"` : a))
  const r = spawnSync(cmd, args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: viaShell,
    timeout: opts.timeout ?? 120000,
    env: opts.env ?? process.env,
  })
  return { ok: r.status === 0, status: r.status, out: (r.stdout || '').trim(), err: (r.stderr || '').trim(), error: r.error }
}
const lastJson = s => {
  for (const line of (s || '').split('\n').reverse()) {
    try {
      if (line.trim().startsWith('{')) return JSON.parse(line)
    } catch {}
  }
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}
const tail = (s, n = 3) => (s || '').split('\n').filter(Boolean).slice(-n).join(' | ')
const PKGMGR = process.platform === 'darwin' ? 'brew install' : process.platform === 'linux' ? 'sudo apt install' : 'install'

console.log(`said-vs-shown doctor · SVS_HOME=${SVS_HOME} · HyperFrames ${CONFIG.hyperframes}\n`)

// 1. node
{
  const [a, b] = process.versions.node.split('.').map(Number)
  if (a > 22 || (a === 22 && b >= 12)) report('PASS', 'node', process.versions.node)
  else report('FAIL', 'node', `${process.versions.node} (need >= 22.12)`, 'install Node.js 22.12+ from https://nodejs.org')
}

// 2. ffmpeg / ffprobe
for (const t of ['ffmpeg', 'ffprobe']) {
  const r = sh(t, ['-version'])
  if (r.ok) report('PASS', t, r.out.split('\n')[0].split(' ').slice(0, 3).join(' '))
  else report('FAIL', t, 'not found', `${PKGMGR} ffmpeg`)
}

// 3. python3
{
  const py = WIN ? 'python' : 'python3'
  const r = sh(py, ['-c', 'import sys; print("%d.%d.%d" % sys.version_info[:3]); sys.exit(sys.version_info < (3, 9))'])
  if (r.ok) report('PASS', 'python3', r.out)
  else report('FAIL', 'python3', r.out ? `${r.out} (need >= 3.9)` : 'not found', `${PKGMGR} python3`)
}

// 4. uv
{
  const r = sh('uv', ['--version'])
  if (r.ok) report('PASS', 'uv', r.out)
  else report('FAIL', 'uv', 'not found', `${PKGMGR} uv  (or https://docs.astral.sh/uv/)`)
}

// 5. node deps in $SVS_HOME/node
let puppeteer = null
{
  const base = path.join(SVS_HOME, 'node', 'package.json')
  const bad = []
  for (const [name, want] of Object.entries(PKG.dependencies)) {
    let have = null
    try {
      have = JSON.parse(fs.readFileSync(path.join(SVS_HOME, 'node', 'node_modules', name, 'package.json'), 'utf8')).version
    } catch {}
    if (have !== want) bad.push(`${name} ${have ?? 'missing'} (want ${want})`)
  }
  if (!bad.length) {
    report('PASS', 'node deps', Object.entries(PKG.dependencies).map(([n, v]) => `${n}@${v}`).join(', '))
    try {
      puppeteer = createRequire(base)('puppeteer-core')
    } catch {}
  } else report('FAIL', 'node deps', bad.join('; '), SETUP)
}

// 6. Chrome (same lookup as receipt.mjs) + a real headless launch
{
  const { findChrome } = await import('./receipt.mjs')
  let exe = null
  try {
    exe = await findChrome()
  } catch (e) {
    report('FAIL', 'chrome', e.message.split('. ')[0], `${SETUP} (or set CHROME_PATH)`)
  }
  if (exe && puppeteer) {
    try {
      const headless = /headless[-_]shell/i.test(exe) ? 'shell' : true
      const browser = await puppeteer.launch({ executablePath: exe, headless, args: ['--hide-scrollbars'] })
      const page = await browser.newPage()
      await page.setContent('<p id=x>said vs shown</p>')
      const txt = await page.$eval('#x', el => el.textContent)
      await browser.close()
      if (txt === 'said vs shown') report('PASS', 'chrome', exe)
      else report('FAIL', 'chrome', `${exe} launched but did not render`, 'set CHROME_PATH to another Chrome')
    } catch (e) {
      report('FAIL', 'chrome', `${exe}: ${e.message.split('\n')[0]}`, `set CHROME_PATH to a working Chrome, or ${SETUP}`)
    }
  } else if (exe) report('WARN', 'chrome', `${exe} (launch not tested: node deps missing)`)
}

// 7. HyperFrames CLI
let hfOk = false
{
  const r = sh('npx', ['-y', HF, '--version'], { timeout: 300000 })
  hfOk = r.ok && r.out.includes(CONFIG.hyperframes)
  if (hfOk) report('PASS', 'hyperframes', `npx ${HF}`)
  else report('FAIL', 'hyperframes', tail(r.err || r.out) || 'npx failed', `check network/npm, then: npx -y ${HF} --version`)
}

// 8. Kokoro python (+ espeak data path length)
let kokoroPy = null
{
  const fromEnv = process.env.HYPERFRAMES_PYTHON
  const venv = [path.join(SVS_HOME, 'kokoro', 'bin', 'python'), path.join(SVS_HOME, 'kokoro', 'Scripts', 'python.exe')].find(p =>
    fs.existsSync(p)
  )
  const py = fromEnv || venv
  if (!py) {
    report('FAIL', 'kokoro venv', `no ${path.join(SVS_HOME, 'kokoro')} and HYPERFRAMES_PYTHON unset`, SETUP)
  } else {
    const r = sh(py, ['-c', 'import kokoro_onnx, soundfile, espeakng_loader as e; print(e.get_data_path())'])
    const src = fromEnv ? 'HYPERFRAMES_PYTHON' : '$SVS_HOME/kokoro'
    if (!r.ok) {
      report('FAIL', 'kokoro venv', `${py} (${src}): ${tail(r.err, 1)}`, `uv pip install --python "${py}" kokoro-onnx soundfile`)
    } else if (r.out.length > 160) {
      report('FAIL', 'kokoro venv', `espeak data path is ${r.out.length} chars (> 160 breaks espeak)`, 'use a shorter SVS_HOME and re-run setup.sh')
    } else {
      kokoroPy = py
      report('PASS', 'kokoro venv', `${py} (${src})`)
    }
  }
}

// 9. ASR engine
if (hfOk) {
  const r = sh('npx', ['-y', HF, 'models', 'list', '--json'])
  const models = lastJson(r.out)?.models ?? []
  const has = e => models.some(m => m.engine === e && m.installed)
  if (has('parakeet')) report('PASS', 'asr', 'parakeet installed')
  else if (has('whisper')) report('PASS', 'asr', `whisper small.en (parakeet not installed: ${SETUP} --with-parakeet)`)
  else report('WARN', 'asr', 'no model yet: Whisper small.en (~470 MB) downloads on first transcription', `${SETUP} --with-parakeet`)
}

// 10. HyperFrames skills: optional. They live in the user's global agent skill folders, which setup only changes
// with the user's consent (setup.sh --no-skills leaves them alone), and the pinned CLI serves the same docs.
if (hfOk) {
  const r = sh('npx', ['-y', HF, 'skills', 'check', '--json'])
  const j = lastJson(r.out)
  const docs = `agents can read HyperFrames docs via \`npx -y ${HF} docs <topic>\` (compositions, data-attributes, gsap)`
  const install = `npx -y ${HF} skills update  (changes the global agent skill folders: ask the user first)`
  if (!j) report('WARN', 'hf skills', `could not read \`skills check\`; ${docs}`, install)
  else if (j.summary?.coreMissing)
    report('WARN', 'hf skills', `${j.summary.coreMissing} core skill(s) not installed; ${docs}`, install)
  else if (j.summary?.outdated) report('WARN', 'hf skills', `${j.summary.outdated} outdated in ${j.location?.replace(os.homedir(), '~')}`, install)
  else report('PASS', 'hf skills', `current in ${j.location?.replace(os.homedir(), '~')}`)
}

// 11. telemetry (information only; never changed here)
if (hfOk) {
  const r = sh('npx', ['-y', HF, 'telemetry', 'status'])
  const st = (r.out.match(/Status:\s*(\w+)/) || [])[1] || 'unknown'
  if (st === 'disabled') report('PASS', 'telemetry', 'disabled')
  else report('WARN', 'telemetry', st, `npx -y ${HF} telemetry disable  (or HYPERFRAMES_NO_TELEMETRY=1)`)
}

// 12. ocr-locate (optional, macOS only)
if (process.platform === 'darwin') {
  const r = sh('swift', ['--version'])
  if (r.ok) report('PASS', 'swift', 'ocr-locate.swift available')
  else report('WARN', 'swift', 'not found; ocr-locate.swift is optional', 'xcode-select --install')
}

// 13. smoke test: ~1 s of Kokoro speech through HyperFrames
if (!SMOKE) report('WARN', 'tts smoke', 'skipped (--no-smoke)')
else if (!hfOk || !kokoroPy) report('FAIL', 'tts smoke', 'skipped: needs hyperframes and the kokoro venv (see above)')
else {
  if (!fs.existsSync(path.join(os.homedir(), '.cache', 'hyperframes', 'tts', 'models', 'kokoro-v1.0.onnx')))
    console.log('      first run: downloading the Kokoro model (~340 MB) for the smoke test; this can take a few minutes')
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'svs-doctor-'))
  const wav = path.join(dir, 'smoke.wav')
  const env = { ...process.env, HYPERFRAMES_PYTHON: kokoroPy }
  const t0 = Date.now()
  const r = sh('npx', ['-y', HF, 'tts', 'Said versus shown.', '-v', CONFIG.voice, '-s', String(CONFIG.speed), '-o', wav, '--json'], {
    env,
    timeout: 600000,
  })
  const j = lastJson(r.out)
  const dur = j?.durationSeconds
  if (r.ok && fs.existsSync(wav) && dur > 0.3 && dur < 5) {
    report('PASS', 'tts smoke', `${dur.toFixed(2)} s of ${CONFIG.voice} in ${((Date.now() - t0) / 1000).toFixed(1)} s`)
  } else {
    report('FAIL', 'tts smoke', j?.error || tail(r.err || r.out) || 'no audio', 'see the error; first run downloads the Kokoro model (~340 MB)')
  }
  fs.rmSync(dir, { recursive: true, force: true })
}

const fails = rows.filter(s => s === 'FAIL').length
const warns = rows.filter(s => s === 'WARN').length
console.log(`\n${fails ? `${fails} FAIL` : 'all checks passed'}${warns ? `, ${warns} WARN` : ''}`)
process.exit(fails ? 1 : 0)
