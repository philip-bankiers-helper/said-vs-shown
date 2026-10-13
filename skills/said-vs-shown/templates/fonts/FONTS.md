# Fonts

Both families are licensed under the SIL Open Font License 1.1. The license text ships next to the files and must stay with them. The files are unmodified copies of the publishers' own builds.

| File | Family / weight | Source | License |
|---|---|---|---|
| `newsreader-latin-300-normal.woff2` | Newsreader 300 | npm `@fontsource/newsreader` 5.3.0, `files/` (Latin subset built by Fontsource from the Newsreader Project's release) | OFL 1.1, `OFL-Newsreader.txt` |
| `newsreader-latin-500-normal.woff2` | Newsreader 500 | same | same |
| `newsreader-latin-700-normal.woff2` | Newsreader 700 | same | same |
| `newsreader-latin-800-normal.woff2` | Newsreader 800 | same | same |
| `IBMPlexMono-Regular-Latin1.woff2` | IBM Plex Mono 400, Latin-1 + common punctuation | npm `@ibm/plex-mono` 2.5.0, `fonts/split/woff2/` (IBM's own pre-split build) | OFL 1.1 with Reserved Font Name "Plex", `OFL-IBMPlexMono.txt` |
| `IBMPlexMono-Regular-Pi.woff2` | IBM Plex Mono 400, arrows / symbols / box drawing | same | same |
| `IBMPlexMono-Medium-Latin1.woff2` | IBM Plex Mono 500, Latin-1 | same | same |
| `IBMPlexMono-Medium-Pi.woff2` | IBM Plex Mono 500, symbols | same | same |
| `IBMPlexMono-SemiBold-Latin1.woff2` | IBM Plex Mono 600, Latin-1 | same | same |
| `IBMPlexMono-SemiBold-Pi.woff2` | IBM Plex Mono 600, symbols | same | same |

Why IBM's own files: IBM reserves the font name "Plex", so a subset made by anyone else is a Modified Version that may not be called "IBM Plex". Redistribute only IBM's builds (never Fontsource's `ibm-plex-mono-*` subsets) and do not subset, convert or rename the family.

To refresh: `npm i --prefix <scratch> @fontsource/newsreader @ibm/plex-mono`, then copy the files listed above.

## @font-face (copy into each composition's `<template><style>`)

Paths are relative to the HyperFrames project root (`video/`), where these files live under `assets/fonts/`. The `unicode-range` values are IBM's (from `@ibm/plex-mono/css/ibm-plex-mono-all.css`).

```css
@font-face { font-family: "Newsreader"; font-weight: 300; src: url("assets/fonts/newsreader-latin-300-normal.woff2") format("woff2"); }
@font-face { font-family: "Newsreader"; font-weight: 500; src: url("assets/fonts/newsreader-latin-500-normal.woff2") format("woff2"); }
@font-face { font-family: "Newsreader"; font-weight: 700; src: url("assets/fonts/newsreader-latin-700-normal.woff2") format("woff2"); }
@font-face { font-family: "Newsreader"; font-weight: 800; src: url("assets/fonts/newsreader-latin-800-normal.woff2") format("woff2"); }
@font-face { font-family: "IBM Plex Mono"; font-weight: 400; src: url("assets/fonts/IBMPlexMono-Regular-Latin1.woff2") format("woff2"); unicode-range: U+0020-007E, U+00A0-00FF, U+0131, U+0152-0153, U+02C6, U+02DA, U+02DC, U+2013-2014, U+2018-201A, U+201C-201E, U+2020-2022, U+2026, U+2030, U+2039-203A, U+2044, U+20AC, U+2122, U+2212, U+FB01-FB02; }
@font-face { font-family: "IBM Plex Mono"; font-weight: 400; src: url("assets/fonts/IBMPlexMono-Regular-Pi.woff2") format("woff2"); unicode-range: U+03C0, U+0E3F, U+2000-200D, U+2010-2012, U+2015, U+2028-2029, U+202F, U+2032-2033, U+203E, U+205F, U+2070, U+2074-2079, U+2080-2089, U+2113, U+2116, U+2126, U+212E, U+2150-2151, U+2153-215E, U+2190-2199, U+21A9-21AA, U+21B0-21B3, U+21B6-21B7, U+21BA-21BB, U+21C4, U+21C6, U+2202, U+2206, U+220F, U+2211, U+2215, U+2219-221A, U+221E, U+222B, U+2236, U+2248, U+2260, U+2264-2265, U+2400-2421, U+2500-259F, U+25CA, U+2713, U+274C, U+2B0E-2B11, U+3000, U+FEFF, U+FFFD; }
/* 500 and 600: the same two rules with Medium / SemiBold */
```

The scene templates declare the Pi file with a narrower range (`U+2190-2199, U+2713, U+2500-259F`: arrows, ✓, box drawing), which is all they use. Either form is fine.
