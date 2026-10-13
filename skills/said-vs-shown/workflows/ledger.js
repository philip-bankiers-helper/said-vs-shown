export const meta = {
  name: 'svs-ledger',
  description: 'Said vs. Shown ledger: verify story claims against captured sources, adversarially refute each story, check other leads',
  phases: [
    { title: 'Verify', detail: 'one verifier per story + lead checkers' },
    { title: 'Refute', detail: 'one adversarial refuter per story' },
  ],
}
// args: { episode: "<abs episode dir>", today: "YYYY-MM-DD",
//         stories: [{ id: "story1", title: "...", srcs: "S01, S06" }],
//         lead_batches: [["4","5","6","7"], ...],
//         source_map: "S01 example.com/page · S02 ..." }
// Agent-neutral copy of these prompts (subagents or one pass at a time): references/ledger-prompts.md. Keep both in sync.
// Save the result's `stories` as ledger/claims.json and its `leads` as ledger/leads.json.
const A = args || {}
const EP = A.episode, CAP = EP + '/ledger/capture', BRIEF = EP + '/input/brief.md'

const CTX = `You are fact-checking sources for a Said vs. Shown episode (an evidence-first explainer video). Today is ${A.today}.
Brief: ${BRIEF}. Captured sources: ${CAP}/Sxx/ (extracted/visible-text.txt is the primary evidence; extracted/page.html; screenshots/).
SOURCE MAP: ${A.source_map}
RULES:
- A "quote" MUST be an exact verbatim substring of that source's visible-text.txt (bracket tags removed). Verify with grep -F before returning it; never paraphrase into the quote field.
- Status: verified (primary source states it) · company_claim (the company's/authors' own capability/performance/result claim) · reported (secondary only) · provider_only (no primary support found) · contradicted · unverifiable (source blocked or silent).
- Note every discrepancy between the brief and the capture.
- Read-only: do not modify files. Do not fetch pages that blocked the capture; never bypass logins, paywalls, CAPTCHAs or bot walls.`

const CLAIM = { type: 'object', properties: {
  claim_id: { type: 'string' }, text: { type: 'string' },
  kind: { type: 'string', enum: ['event', 'date', 'number', 'limit', 'interpretation', 'availability'] },
  status: { type: 'string', enum: ['verified', 'company_claim', 'reported', 'provider_only', 'contradicted', 'unverifiable'] },
  source_ids: { type: 'array', items: { type: 'string' } }, quote: { type: 'string' }, notes: { type: 'string' } },
  required: ['claim_id', 'text', 'kind', 'status', 'source_ids', 'quote', 'notes'] }
const STORY = { type: 'object', properties: {
  story_id: { type: 'string' }, claims: { type: 'array', items: CLAIM },
  receipt_candidates: { type: 'array', items: { type: 'object', properties: {
    source_id: { type: 'string' }, quote: { type: 'string' }, claim_ids: { type: 'array', items: { type: 'string' } },
    screenshot: { type: 'string' }, why: { type: 'string' } }, required: ['source_id', 'quote', 'claim_ids', 'screenshot', 'why'] } },
  discrepancies: { type: 'array', items: { type: 'string' } } },
  required: ['story_id', 'claims', 'receipt_candidates', 'discrepancies'] }
const REFUTE = { type: 'object', properties: {
  story_id: { type: 'string' },
  verdicts: { type: 'array', items: { type: 'object', properties: {
    claim_id: { type: 'string' }, upheld: { type: 'boolean' }, problem: { type: 'string' }, fix: { type: 'string' } },
    required: ['claim_id', 'upheld', 'problem', 'fix'] } },
  narration_risks: { type: 'array', items: { type: 'string' } } }, required: ['story_id', 'verdicts', 'narration_risks'] }
const LEADS = { type: 'object', properties: { leads: { type: 'array', items: { type: 'object', properties: {
  lead_id: { type: 'string' }, title: { type: 'string' }, date: { type: 'string' }, one_liner: { type: 'string' }, caution: { type: 'string' },
  status: { type: 'string', enum: ['verified', 'company_claim', 'reported', 'provider_only', 'contradicted', 'unverifiable', 'older_background'] },
  source_ids: { type: 'array', items: { type: 'string' } }, quote: { type: 'string' }, discrepancies: { type: 'string' } },
  required: ['lead_id', 'title', 'date', 'one_liner', 'caution', 'status', 'source_ids', 'quote', 'discrepancies'] } } }, required: ['leads'] }

phase('Verify')
const storyRuns = pipeline(A.stories || [],
  s => agent(`${CTX}\n\nTASK: Verify the brief's story "${s.title}" (sources ${s.srcs}). Break it into atomic claims a narrator might say (what happened, dates, numbers, availability, meaning, stated limits). Find exact support for each. Propose 2-4 receipt_candidates: short verbatim sentences visually prominent on the page (name the screenshot). Return story_id "${s.id}".`,
    { label: `verify:${s.id}`, phase: 'Verify', schema: STORY }),
  (res, s) => res && agent(`${CTX}\n\nTASK (ADVERSARIAL): Try to REFUTE each claim in this ledger for "${s.title}": (1) grep -F the quote — verbatim? (2) does it support the claim IN CONTEXT? (3) is the status right (a vendor's own performance number is company_claim; future availability is not availability)? Default upheld=false when uncertain. List narration_risks.\nLEDGER:\n${JSON.stringify(res, null, 1)}`,
    { label: `refute:${s.id}`, phase: 'Refute', schema: REFUTE }).then(v => ({ story_id: s.id, ledger: res, refute: v })))
const leadRuns = parallel((A.lead_batches || []).map(ids => () => agent(`${CTX}\n\nTASK: For the brief's other leads ${ids.join(', ')}, produce companion-page cards: check each key fact and date against its capture; use older_background for items older than the episode window; leads without a URL are provider_only. Neutral wording; keep the brief's cautions.`,
  { label: `leads:${ids[0]}-${ids[ids.length - 1]}`, phase: 'Verify', schema: LEADS })))
const [stories, leads] = await Promise.all([storyRuns, leadRuns])
return { stories: stories.filter(Boolean), leads: leads.filter(Boolean).flatMap(l => l.leads) }
