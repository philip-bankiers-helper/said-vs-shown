# AI brief, 2026-10-08

Window: Oct 5–8, 2026

## Selected stories

### 1. Mathematics: a public artifact can be checked

**October 6.** OpenAI released mathematical manuscripts it says were produced by an internal, unreleased model. Some results come with Lean formalizations. Repository counts are changing and use different denominators; the video leaves them out.
Sources: https://github.com/openai/math · https://openai.com/index/sharing-ai-progress-in-mathematics/
Meaning: a formal proof lets a computer check whether an argument establishes a precise statement under its assumptions.
Cautions: OpenAI warns that unformalized results could have issues. A formal check does not establish novelty, significance, or that the formal statement matches the paper's informal claim. This production does not compile the proofs.

## Other leads

| ID | Lead and date | Source | Caution |
|---|---|---|---|
| 2 | Thinking Machines on nondeterministic LLM inference (research Sep 10, 2025; resurfaced Oct 7) | https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ | Older research; temperature zero alone is not a guarantee. |
| 3 | Cortex Harness: remote human guidance for robots (Oct 6) | https://cortexrobot.ai/research/introducing-cortex-harness/ | Company announcement; curated demos and a waitlist, no intervention rates. |

## Guardrails

- Never narrate the repository's manuscript or formalization counts (unstable).
- Attribute provenance: the manuscripts are ones OpenAI *says* an internal model produced.
- A Lean formalization is not "machine-verified" unless a check was run; this production ran none.
