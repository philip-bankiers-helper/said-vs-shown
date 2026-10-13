#!/usr/bin/env node
// suggest.mjs — list the visible sentences of a page, so demo.py can suggest one when a quote is not found.
//
// usage: node suggest.mjs --url <u>
// Prints JSON: {"url": "...", "sentences": ["...", ...]} (visible paragraph, list-item, heading, quote and
// table-cell text, split into sentences, 20–300 characters each). Same browser rules as engine/receipt.mjs:
// headless Chrome with its own identity, nothing clicked, no consent accepted, no login.

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ENGINE = path.join(HERE, '..', 'engine')
const CONFIG = JSON.parse(fs.readFileSync(path.join(ENGINE, 'config.json'), 'utf8'))
const expandHome = p => (p === '~' || p.startsWith('~/') ? path.join(os.homedir(), p.slice(1)) : p)
const SVS_HOME = path.resolve(expandHome(process.env.SVS_HOME || CONFIG.home || '~/.said-vs-shown'))

function requireDep(name) {
  for (const base of [path.join(SVS_HOME, 'node', 'package.json'), path.join(ENGINE, 'package.json')]) {
    try {
      return createRequire(base)(name)
    } catch (e) {
      if (e.code !== 'MODULE_NOT_FOUND') throw e
    }
  }
  return null
}

const USAGE = 'usage: node suggest.mjs --url <u>\n' +
  'Prints JSON {"url", "sentences": [...]}: the visible sentences of the page (headless Chrome, nothing clicked).'
const { values: opts } = parseArgs({ options: { url: { type: 'string' }, help: { type: 'boolean', short: 'h' } } })
if (opts.help) {
  console.log(USAGE)
  process.exit(0)
}
if (!opts.url) {
  console.error(USAGE)
  process.exit(2)
}
const puppeteer = requireDep('puppeteer-core')
if (!puppeteer) {
  console.error(`puppeteer-core not found; run: sh "${path.join(ENGINE, 'setup.sh')}"`)
  process.exit(2)
}
const executablePath = execFileSync(process.execPath, [path.join(ENGINE, 'receipt.mjs'), '--find-chrome']).toString().trim()
const headless = /headless[-_]shell/i.test(executablePath) ? 'shell' : true
const browser = await puppeteer.launch({ executablePath, headless, args: ['--hide-scrollbars'] })
let sentences = []
try {
  const page = await browser.newPage()
  await page.setViewport({ width: 1440, height: 900 })
  await page.goto(opts.url, { waitUntil: 'networkidle2', timeout: 60000 }).catch(() => null)
  await new Promise(r => setTimeout(r, 800))
  sentences = await page.evaluate(() => {
    const visible = e => {
      const cs = getComputedStyle(e)
      const r = e.getBoundingClientRect()
      return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0
    }
    const out = []
    for (const e of document.querySelectorAll('p, li, h1, h2, h3, h4, blockquote, td, dd, figcaption')) {
      if (!visible(e)) continue
      const t = (e.innerText || '').replace(/\s+/g, ' ').trim()
      for (const s of t.split(/(?<=[.!?])\s+(?=[A-Z0-9"“(])/)) if (s.length >= 20 && s.length <= 300) out.push(s)
    }
    return [...new Set(out)]
  })
} finally {
  await browser.close()
}
console.log(JSON.stringify({ url: opts.url, sentences }))
