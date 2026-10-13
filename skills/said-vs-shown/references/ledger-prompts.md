# Ledger prompts (stage 3)

The same prompts as `workflows/ledger.js` (the Claude Code Workflow script), written out for any agent. Keep the two in sync.

Fill in the `{placeholders}`:
- `{EPISODE}`: the episode root (absolute path); `{TODAY}`: today's date (YYYY-MM-DD).
- `{SOURCE_MAP}`: one `Sxx domain/path` per entry of `ledger/sources.json`, joined with ` · `.
- `{STORY_ID}`, `{STORY_TITLE}`, `{SRCS}`: per selected story, e.g. `story1`, the brief's story title, `S01, S02` (its sources' ids).
- `{LEAD_IDS}`: a batch of 3–5 of the brief's other lead ids (see `references/brief-format.md`).

Every pass is read-only on the captures. You (the orchestrating agent) write the result files.

How to run them:
- **Claude Code with the Workflow tool:** `workflows/ledger.js`, args in its header. Save the result's `stories` as `ledger/claims.json` and its `leads` (already flattened) as `ledger/leads.json`.
- **An agent that runs subagents:** one subagent per prompt. Run the verifiers and lead checkers in parallel, then one refuter per story on its verifier's result.
- **No subagents:** run the prompts one after another yourself. Save each result under `ledger/work/` before starting the next. Run every refuter as a separate pass that works from the saved verifier file, not from what you remember of writing it. Default to "not upheld" when unsure.

Each result is JSON in the shape given under "Returns".

## Shared context (put it before every prompt)

```
You are fact-checking sources for a Said vs. Shown episode (an evidence-first explainer video). Today is {TODAY}.
Brief: {EPISODE}/input/brief.md. Captured sources: {EPISODE}/ledger/capture/Sxx/ (extracted/visible-text.txt is the primary evidence; extracted/page.html; screenshots/).
SOURCE MAP: {SOURCE_MAP}
RULES:
- A "quote" MUST be an exact verbatim substring of that source's visible-text.txt (bracket tags removed). Verify it with grep -F before returning it; never paraphrase into the quote field.
- Status: verified (a primary source states it) · company_claim (the company's or authors' own claim about capability, performance or results) · reported (secondary only) · provider_only (no primary support found) · contradicted · unverifiable (source blocked or silent).
- Note every discrepancy between the brief and the capture.
- Read-only: do not modify files. Do not fetch pages that blocked the capture; never bypass logins, paywalls, CAPTCHAs or bot walls.
```

## Verifier (one per selected story)

```
TASK: Verify the brief's story "{STORY_TITLE}" (sources {SRCS}). Break it into atomic claims a narrator might say (what happened, dates, numbers, availability, meaning, stated limits). Find exact support for each. Propose 2-4 receipt_candidates: short verbatim sentences visually prominent on the page (name the screenshot). Return story_id "{STORY_ID}".
```

Returns:

```
{story_id, claims: [{claim_id, text, kind: event|date|number|limit|interpretation|availability,
                     status, source_ids[], quote, notes}],
 receipt_candidates: [{source_id, quote, claim_ids[], screenshot, why}],
 discrepancies: [string]}
```

Without subagents, save it to `{EPISODE}/ledger/work/{STORY_ID}.verify.json`.

## Refuter (one per story, after its verifier)

```
TASK (ADVERSARIAL): Try to REFUTE each claim in this ledger for "{STORY_TITLE}": (1) grep -F the quote: is it verbatim? (2) does it support the claim IN CONTEXT? (3) is the status right (a vendor's own performance number is company_claim; future availability is not availability)? Default upheld=false when uncertain. List narration_risks.
LEDGER:
{the verifier's JSON result}
```

Returns:

```
{story_id, verdicts: [{claim_id, upheld, problem, fix}], narration_risks: [string]}
```

Without subagents, save it to `{EPISODE}/ledger/work/{STORY_ID}.refute.json`.

## Lead checker (one per batch of 3–5 other leads)

```
TASK: For the brief's other leads {LEAD_IDS}, produce companion-page cards: check each key fact and date against its capture; use older_background for items older than the episode window; leads without a URL are provider_only. Neutral wording; keep the brief's cautions.
```

Returns:

```
{leads: [{lead_id, title, date, one_liner, caution,
          status: verified|company_claim|reported|provider_only|contradicted|unverifiable|older_background,
          source_ids[], quote, discrepancies}]}
```

## Result files

- `ledger/claims.json` = `[{story_id, ledger: <verifier result>, refute: <refuter result>}, ...]`, one entry per selected story.
- `ledger/leads.json` = every lead checker's `leads[]`, concatenated.
- Apply every refuter fix (`upheld: false`) to the wording before the script (stage 5), and keep the ledger as written.

A worked example of both files: `references/example/ledger/`.
