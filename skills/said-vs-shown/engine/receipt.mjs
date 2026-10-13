#!/usr/bin/env node
// receipt.mjs — capture a real source page with a verbatim quote located on it.
//
// Output: one 2x viewport screenshot with the quote scrolled to ~42% height, plus a JSON
// sidecar holding the quote's line rects (viewport CSS px and 0–1 fractions), the page
// URL/title/status and a sha256 of the PNG. The video pushes in on the real page and sweeps
// a highlighter over exactly those rects.
//
// Never accepts consent dialogs, never logs in, never spoofs a browser identity (the user
// agent is Chrome's own). Fixed/sticky overlays are hidden visually only; nothing is clicked.
// A page that refuses headless Chrome, or a quote that is not on the page, is reported as
// found:false (JSON only, no PNG, exit 1) and falls back to a labelled quote card upstream.
//
// usage: node receipt.mjs --url <u> --quote "<verbatim text>" --out <Rnn-name.png>
//          [--width 1440] [--height 900] [--scale 2] [--anchor 0.42] [--nojs 1]
//        node receipt.mjs --find-chrome        print the Chrome this tool would use
//
// --nojs 1 renders a SAVED capture (file://…/page.html or a plain path) as static HTML, for
// pages whose client app breaks offline. Use it only on captures this project already obtained.
// A file:// url under an episode is stored relative (capture/Sxx/extracted/page.html), never
// as an absolute path.
//
// Chrome lookup order: $CHROME_PATH, installs under $SVS_HOME/chrome, the build pinned by our puppeteer-core in
// ~/.cache/puppeteer (other builds there are ignored), then common system Chrome/Chromium paths. puppeteer-core is resolved from $SVS_HOME/node
// (installed by setup.sh), falling back to a local `npm i` in this folder.

import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import crypto from 'node:crypto'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'

const ENGINE = path.dirname(fileURLToPath(import.meta.url))
const CONFIG = JSON.parse(fs.readFileSync(path.join(ENGINE, 'config.json'), 'utf8'))

const expandHome = p => (p === '~' || p.startsWith('~/') || p.startsWith('~\\') ? path.join(os.homedir(), p.slice(1)) : p)
const SVS_HOME = path.resolve(expandHome(process.env.SVS_HOME || CONFIG.home))

// --- module resolution: $SVS_HOME/node first, then this folder's own node_modules ---------
function requireDep(name) {
  const bases = [path.join(SVS_HOME, 'node', 'package.json'), path.join(ENGINE, 'package.json')]
  for (const base of bases) {
    try {
      return createRequire(base)(name)
    } catch (e) {
      if (e.code !== 'MODULE_NOT_FOUND') throw e
    }
  }
  return null
}

// --- Chrome lookup ----------------------------------------------------------------------------
function versionKey(buildId) {
  return String(buildId).split(/[.\-_]/).map(n => (/^\d+$/.test(n) ? n.padStart(8, '0') : n)).join('.')
}

async function installedIn(browsers, cacheDir) {
  if (!browsers || !fs.existsSync(cacheDir)) return []
  const platform = browsers.detectBrowserPlatform()
  let found = []
  try {
    found = await browsers.getInstalledBrowsers({ cacheDir })
  } catch {
    return []
  }
  const pref = { 'chrome-headless-shell': 0, chrome: 1, chromium: 2 }
  return found
    .filter(b => b.platform === platform && b.browser in pref)
    .sort((a, b) => pref[a.browser] - pref[b.browser] || versionKey(b.buildId).localeCompare(versionKey(a.buildId)))
    .map(b => browsers.computeExecutablePath({ cacheDir, browser: b.browser, buildId: b.buildId, platform: b.platform }))
    .filter(p => fs.existsSync(p))
}

function systemChromes() {
  const home = os.homedir()
  const local = process.env.LOCALAPPDATA || path.join(home, 'AppData', 'Local')
  const pf = [process.env.PROGRAMFILES, process.env['PROGRAMFILES(X86)']].filter(Boolean)
  const byPlatform = {
    darwin: [
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      path.join(home, 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
      '/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    ],
    linux: [
      '/usr/bin/google-chrome-stable',
      '/usr/bin/google-chrome',
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/snap/bin/chromium',
    ],
    win32: [
      ...pf.map(p => path.join(p, 'Google', 'Chrome', 'Application', 'chrome.exe')),
      path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ],
  }
  return (byPlatform[process.platform] || []).filter(p => fs.existsSync(p))
}

export async function findChrome() {
  if (process.env.CHROME_PATH) {
    if (fs.existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH
    throw new Error(`CHROME_PATH is set but does not exist: ${process.env.CHROME_PATH}`)
  }
  const browsers = requireDep('@puppeteer/browsers')
  // ~/.cache/puppeteer is shared with other projects: use only the build our puppeteer-core pins, so a stale
  // build left there by something else never wins over a current system Chrome
  const pinned = requireDep('puppeteer-core')?.PUPPETEER_REVISIONS?.['chrome-headless-shell']
  const shared = pinned
    ? (await installedIn(browsers, path.join(os.homedir(), '.cache', 'puppeteer'))).filter(p => p.includes(pinned))
    : []
  const candidates = [...(await installedIn(browsers, path.join(SVS_HOME, 'chrome'))), ...shared, ...systemChromes()]
  if (candidates.length) return candidates[0]
  throw new Error(
    `No usable Chrome found. Run: sh "${path.join(ENGINE, 'setup.sh')}" (installs chrome-headless-shell into $SVS_HOME/chrome), ` +
      'or set CHROME_PATH to a Chrome/Chromium executable.'
  )
}

// --- url handling -----------------------------------------------------------------------------
function toNavigable(u) {
  // file://<relative path> is not a valid file URL (its first segment would be read as a host): resolve it
  if (/^file:\/\/[^/]/i.test(u) && fs.existsSync(decodeURIComponent(u.slice(7)))) return pathToFileURL(path.resolve(decodeURIComponent(u.slice(7)))).href
  if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return u
  if (fs.existsSync(u)) return pathToFileURL(path.resolve(u)).href
  return u
}

// A file:// url is stored relative to its episode's ledger/ (capture/Sxx/extracted/page.html),
// else relative to the output file's folder. Never an absolute local path.
function publicUrl(u, outFile) {
  if (!u || !u.startsWith('file:')) return u
  let p
  try {
    p = fileURLToPath(u)
  } catch {
    return 'file'
  }
  const parts = p.split(path.sep)
  const li = parts.lastIndexOf('ledger')
  if (li >= 0 && li < parts.length - 1) return parts.slice(li + 1).join('/')
  return path.relative(path.dirname(path.resolve(outFile)), p).split(path.sep).join('/')
}

function scrubPaths(s, outFile) {
  if (typeof s !== 'string') return s
  return s.replace(/file:\/\/[^\s'")]+/g, m => publicUrl(m, outFile)).split(os.homedir()).join('~')
}

// --- main -------------------------------------------------------------------------------------
async function main() {
  let opts
  try {
    ;({ values: opts } = parseArgs({
      options: {
        url: { type: 'string' },
        quote: { type: 'string' },
        out: { type: 'string' },
        width: { type: 'string', default: '1440' },
        height: { type: 'string', default: '900' },
        scale: { type: 'string', default: '2' },
        anchor: { type: 'string', default: '0.42' },
        nojs: { type: 'string' },
        'find-chrome': { type: 'boolean', default: false },
        help: { type: 'boolean', short: 'h', default: false },
      },
    }))
  } catch (e) {
    console.error(e.message)
    process.exit(2)
  }

  if (opts.help) {
    console.log(
      'usage: node receipt.mjs --url <u> --quote "<verbatim text>" --out <Rnn-name.png>\n' +
        '         [--width 1440] [--height 900] [--scale 2] [--anchor 0.42] [--nojs 1]\n' +
        '       node receipt.mjs --find-chrome        print the Chrome this tool would use\n' +
        '--url takes a web URL, a plain path to a saved page.html, or an absolute file:// URL.\n' +
        '--nojs 1 renders a saved capture as static HTML (only captures this project already obtained).\n' +
        'Writes <out>.png and <out>.json (found, lines, viewport, status). Exit 0 found, 1 not found, 2 usage/setup.'
    )
    process.exit(0)
  }

  if (opts['find-chrome']) {
    try {
      console.log(await findChrome())
      process.exit(0)
    } catch (e) {
      console.error(e.message)
      process.exit(1)
    }
  }

  const { url, quote, out } = opts
  if (!url || !quote || !out || !out.endsWith('.png')) {
    console.error('usage: receipt.mjs --url <u> --quote "<text>" --out <file.png> [--nojs 1]')
    process.exit(2)
  }
  const W = +opts.width, H = +opts.height, SCALE = +opts.scale, ANCHOR = +opts.anchor
  const NOJS = opts.nojs !== undefined && opts.nojs !== '0' && opts.nojs !== 'false'
  const jsonOut = out.replace(/\.png$/, '.json')

  const puppeteer = requireDep('puppeteer-core')
  if (!puppeteer) {
    console.error(`puppeteer-core not found in ${path.join(SVS_HOME, 'node')}. Run: sh "${path.join(ENGINE, 'setup.sh')}" (or npm i in ${ENGINE}).`)
    process.exit(2)
  }
  let executablePath
  try {
    executablePath = await findChrome()
  } catch (e) {
    console.error(e.message)
    process.exit(2)
  }

  const target = toNavigable(url)
  const result = {
    url: publicUrl(target, out),
    quote,
    found: false,
    capturedAt: new Date().toISOString(),
    viewport: { width: W, height: H, scale: SCALE },
    nojs: NOJS,
  }
  const headless = /headless[-_]shell/i.test(executablePath) ? 'shell' : true
  const browser = await puppeteer.launch({ executablePath, headless, args: ['--hide-scrollbars'] })
  let page
  try {
    page = await browser.newPage()
    await page.setViewport({ width: W, height: H, deviceScaleFactor: SCALE })
    if (NOJS) await page.setJavaScriptEnabled(false)
    await page.emulateMediaFeatures([
      { name: 'prefers-color-scheme', value: 'light' },
      { name: 'prefers-reduced-motion', value: 'reduce' },
    ])
    let resp = null
    try {
      resp = await page.goto(target, { waitUntil: 'networkidle2', timeout: 60000 })
    } catch (e) {
      result.navError = e.message
    }
    result.status = resp?.status?.() ?? null
    result.finalUrl = publicUrl(page.url(), out)
    result.title = await page.title().catch(() => '')
    await new Promise(r => setTimeout(r, 1200))
    // our locate script below needs JS; the page's own scripts never ran
    if (NOJS) await page.setJavaScriptEnabled(true)

    const loc = await page.evaluate(
      (quote, anchor) => {
        // hide fixed/sticky chrome (cookie bars, sticky navs): visual only, nothing is clicked
        for (const el of document.querySelectorAll('body *')) {
          const pos = getComputedStyle(el).position
          if (pos === 'fixed' || pos === 'sticky') el.style.setProperty('visibility', 'hidden', 'important')
        }
        const norm = s => s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, '-').replace(/\s+/g, ' ')
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
          acceptNode: n => {
            const p = n.parentElement
            if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) return NodeFilter.FILTER_REJECT
            const cs = getComputedStyle(p)
            return cs.display === 'none' || cs.visibility === 'hidden' ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
          },
        })
        // concatenate normalized text, remembering where each char came from
        let flat = '', prevSpace = true
        const map = []
        for (let n; (n = walker.nextNode()); ) {
          const t = n.nodeValue
          for (let i = 0; i < t.length; i++) {
            const c = norm(t[i])
            if (c === ' ') {
              if (prevSpace) continue
              prevSpace = true
            } else prevSpace = false
            flat += c
            map.push([n, i])
          }
        }
        const q = norm(quote).trim()
        const at = q ? flat.indexOf(q) : -1
        if (at < 0) return { found: false, sample: flat.slice(0, 300) }
        const [sn, so] = map[at], [en, eo] = map[at + q.length - 1]
        const range = document.createRange()
        range.setStart(sn, so)
        range.setEnd(en, eo + 1)
        const box = range.getBoundingClientRect()
        window.scrollBy(0, box.top - innerHeight * anchor)
        const rects = [...range.getClientRects()].filter(r => r.width > 2 && r.height > 2)
        // merge rects that sit on the same line
        const lines = []
        for (const r of rects) {
          const l = lines.find(l => Math.abs(l.y - r.top) < r.height * 0.5)
          if (l) {
            l.x2 = Math.max(l.x2, r.right)
            l.x = Math.min(l.x, r.left)
            l.h = Math.max(l.h, r.height)
          } else lines.push({ x: r.left, y: r.top, x2: r.right, h: r.height })
        }
        const block = (sn.parentElement.closest('p,li,blockquote,h1,h2,h3,td,div') || sn.parentElement).getBoundingClientRect()
        return {
          found: true,
          lines: lines.map(l => ({ x: l.x, y: l.y, w: l.x2 - l.x, h: l.h })),
          block: { x: block.left, y: block.top, w: block.width, h: block.height },
          fontSize: parseFloat(getComputedStyle(sn.parentElement).fontSize),
        }
      },
      quote,
      ANCHOR
    )
    Object.assign(result, loc)

    fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true })
    if (loc.found) {
      const frac = r => ({ x: r.x / W, y: r.y / H, w: r.w / W, h: r.h / H })
      result.linesFrac = loc.lines.map(frac)
      result.blockFrac = frac(loc.block)
      await page.screenshot({ path: out, type: 'png' })
      result.image = { path: path.basename(out), width: W * SCALE, height: H * SCALE }
      result.sha256 = crypto.createHash('sha256').update(fs.readFileSync(out)).digest('hex')
    }
  } catch (e) {
    result.found = false
    result.error = e.message
  } finally {
    await browser.close()
  }
  // a miss never leaves a PNG behind (not even one from an earlier run at the same path)
  if (!result.found) fs.rmSync(out, { force: true })
  result.error = scrubPaths(result.error, out)
  result.navError = scrubPaths(result.navError, out)
  result.sample = scrubPaths(result.sample, out)
  fs.mkdirSync(path.dirname(path.resolve(jsonOut)), { recursive: true })
  fs.writeFileSync(jsonOut, JSON.stringify(result, null, 2) + '\n', 'utf8')
  console.log(
    JSON.stringify({
      found: result.found,
      status: result.status,
      lines: result.lines?.length ?? 0,
      out: result.found ? out : null,
      json: jsonOut,
      error: result.error ?? result.navError,
    })
  )
  process.exit(result.found ? 0 : 1)
}

const isMain = (() => {
  try {
    return fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url))
  } catch {
    return false
  }
})()
if (isMain) await main()
