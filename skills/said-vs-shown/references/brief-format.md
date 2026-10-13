# Brief format

A brief is one Markdown file: the research the episode is built from. `engine/capture.sh` captures every `http(s)` URL in it, in order of appearance (the sources of the selected stories first, via `ledger/selected.txt`), so link primary sources directly: the announcement, the repository, the paper, the release notes. A claim with no linked source can only ever be badged *Provider*.

```markdown
# <Edition> brief, <YYYY-MM-DD>

Window: <Oct 5–8, 2026>

## Selected stories

### 1. <Topic>: <one-line angle>
What happened, with dates and numbers.
Sources: <primary URL> · <secondary URL>
Cautions: what the sources don't establish.

### 2. ...   (up to 3)

## Other leads

| ID | Lead and date | Source | Caution |
|---|---|---|---|
| 4 | ... | https://... | ... |

## Guardrails

- Numbers that are unstable (never narrate them), wording to avoid, claims that must be attributed.
```

- **Window:** the dates the episode covers. The episode date (stage 1) is the end of the window, or today when the brief has none. Items older than the window become *Older* background.
- **Selected stories:** 1–3, numbered. If the brief selects none, the skill picks up to 3 by impact × novelty × evidence and records why in `edit/selection.md`.
- **Other leads:** numbered after the stories (stories 1–3, leads from 4). The lead checkers and the companion page use these ids; a lead without a URL is *Provider*.
- **Guardrails** are binding: the script follows them, and the refuters check against them.

A complete small brief, the one the worked example is built from: `references/example/input/brief.md`.
