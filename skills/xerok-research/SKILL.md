---
name: xerok-research
description: Use when the user asks for deep, exhaustive, or cited research on an open-ended technical/market question that needs evidence from the open web and a structured, source-grounded report — "deep research", "pesquisa profunda", "investiga a fundo", "quero saber tudo sobre", benchmarks/comparisons/buying decisions across many sources. Not for simple lookups, single-source facts, or coding tasks.
---

# XEROK RESEARCH

A four-stage engine that turns one question into a **cited report**: a typed
state object is handed through **Plan → Research → Write → Edit**. You (the main
session) are the **orchestrator**: you keep the state, fan out isolated-context
sub-agents (opus for heavy reasoning, sonnet for breadth), aggregate their
evidence deterministically, and enforce a hard output contract.

Core principle: **separate finding evidence from writing, and writing from
formatting.** The grounding and the presentation contract — not raw search
volume — are what make the report trustworthy.

## Complexity Contract (read before running)

- **Cost.** `deep` fans out ~10–16 sub-agents + dozens of web lookups (high
  token + tool spend). `standard` ~6–9. `quick` ~1–3. Tell the user the depth
  you're running.
- **Use when:** the question is open-ended, spans many sources, and the user
  wants a structured, cited answer (benchmarks, comparisons, buying/architecture
  decisions, landscapes, "everything about X").
- **Do NOT use when:** a single lookup or your own knowledge answers it, it's a
  coding/file task, or the user wants a quick chat reply. Just answer directly.
- **Fast path / fallback.** Default to `quick` unless the user signals depth.
  Any `xerok.py` step is fail-soft: if a script errors, log it and continue with
  the unprocessed text — never block the report on tooling.

## Depth modes

| depth | research_queries | lanes dispatched | section writers | when |
|-------|------------------|------------------|-----------------|------|
| `quick` | 6–10 | 1 (evidence) | inline (you write) | fast, single TL;DR brief |
| `standard` | 18–28 | 3 (evidence, comparator, critic) | 2–3 parallel | default deep research |
| `deep` | 36–64 | 5 (all) | 4 parallel | exhaustive, high-stakes |

Bundled assets (read on demand, not all upfront):
`references/output-contract.md` (the report spec), `references/specialists.md`
(role prompts to paste into dispatches), `scripts/xerok.py` (the deterministic
engine). `SCRIPT = ${CLAUDE_SKILL_DIR}/scripts/xerok.py`.

## Typed state & memory bank

State lives in files so it survives compaction and crosses the sub-agent context
boundary (sub-agents share no memory; the **only** channels are the dispatch
prompt in and their final message + the files they write out).

```
xerok-runs/<id>/
  state.json            # question, language, depth, sub_questions,
                        #   research_queries, acceptance_criteria, numeric_spine
  evidence/<lane>.jsonl # each lane appends its findings (strict JSON schema)
  evidence/bank.jsonl   # deduped, source-scored (built by merge-evidence)
  coverage.json         # per-sub-question coverage + gaps (built by merge-evidence)
  numeric_spine.md      # must-include numbers + outline
  sections/<slug>.md    # one file per written section
  report.md             # the final cited report
```

---

## Stage 01 — Plan (scope what's really being asked)

1. Decide **depth** (default `quick`; `standard`/`deep` if the user signals it or
   the question is broad). Detect the **answer language** from the question.
2. Create the run: `!`python3 $SCRIPT init "<question>" --depth <depth> --lang <lang>`` →
   capture the printed `RUN_DIR`.
3. Build the **typed plan**. For `standard`/`deep`, dispatch the **architect**
   (opus) from `references/specialists.md`; for `quick`, do it inline. Result
   (written into `state.json`): `sub_questions` (5–12, MECE, in answer order),
   `research_queries` (per depth count), `acceptance_criteria` (literal/regex
   strings the report must contain), `numeric_spine` targets, and an entity
   **disambiguation** table if terms are ambiguous.
4. Gate: the plan is done when every sub-question maps to ≥1 research query and
   acceptance criteria exist that `xerok.py validate` can later check.

## Stage 02 — Research (evidence from the open web)

1. Split `research_queries` across the lanes for this depth. Dispatch the lanes
   **in parallel, in one message** (Agent tool, isolated context). Use the
   role blocks + shared header from `references/specialists.md`; pin the model
   per lane (evidence/comparator/horizon → **sonnet**; mechanism/critic →
   **opus**). Pass each lane: `RUN_DIR`, the question, its sub-questions, its
   query slice, the evidence JSONL schema, and its web budget.
2. Each lane writes `evidence/<lane>.jsonl` and returns a short manifest only
   (counts, top findings, gaps, conflicts) — keep their raw dumps out of your
   context.
3. Aggregate deterministically:
   `!`python3 $SCRIPT merge-evidence <RUN_DIR>`` → dedups, scores source primacy
   (flags homepages/social), writes `bank.jsonl`, and reports **coverage + gaps**.
4. **Evidence-sufficiency gate.** If `coverage.json` shows gaps (sub-questions
   with `< min-evidence`) or too many non-primary sources, dispatch 1–2 targeted
   **gap-fill** searches (reuse the evidence/critic role with the missing
   sub-questions). Re-run `merge-evidence`. Cap: 2 gap-fill rounds.

## Stage 03 — Write (section by section, grounded in evidence)

1. **numeric_spine + outline** (opus, or inline for quick): from `bank.jsonl` +
   `coverage.json`, list the must-include numbers/specs with their `[n]`, and the
   section outline. Write `numeric_spine.md`.
2. Read `references/output-contract.md`. Write the **opening** (title + executive
   summary with numbered core conclusions).
3. Write **body + Comprehensive-Analysis sections** with `section_writer` (opus),
   in parallel where independent. Each section reads only its evidence slice from
   `bank.jsonl`, uses the global `[n]` numbers, and is written to
   `sections/<slug>.md`.
4. **Per-section quality loop:** for each section run `grounding_scorer`
   (sonnet) → if score < 75 or the not-hollow gate fails, regenerate with the
   listed fixes. **Cap 2 retries**, then accept the best and move on.
5. Assemble sections in contract order into `report.md`.

## Stage 04 — Edit (fill gaps, enforce the contract, tighten)

1. **refiner** (sonnet): enforce the contract — ensure Scope (incl. "does NOT
   establish"), Comprehensive Analysis answering each sub-question 1:1, and
   Limitations all exist; merge duplicates; fill coverage gaps; strip AI-writing
   tells. Citations stay intact.
2. **readability_rewrite** (opus): final flow pass, no new facts, no dropped
   citations, language stays locked.
3. **Deterministic post-pass** (NO LLM, idempotent, fail-soft):
   `!`python3 $SCRIPT postpass <RUN_DIR>/report.md`` → renumber/dedup citations,
   rebuild the Sources block, clamp em-dashes, despace CJK, normalize whitespace,
   flag long paragraphs.
4. **Validate against the plan:**
   `!`python3 $SCRIPT validate <RUN_DIR> <RUN_DIR>/report.md`` → checks citations
   resolve, primary-source ratio ≥0.7, Limitations present, every sub-question
   covered, numeric_spine present, acceptance criteria met. On failure, do one
   targeted fix round (more evidence or a section rewrite), then re-postpass +
   re-validate. `!`python3 $SCRIPT metrics <RUN_DIR>/report.md`` for the summary.
5. Deliver `report.md` to the user as the **cited final report**. Tell them the
   run dir, depth, source count, and any residual gaps the validator flagged.

---

## How to dispatch a sub-agent

Use the Agent tool with an isolated `subagent_type` (e.g. `general-purpose`,
which has web tools and can write files; `Explore` for read-only search). Pin
`model` to `opus` or `sonnet` per the lane. Build the `prompt` as: the shared
header from `references/specialists.md` + the lane's role block + the concrete
slice (RUN_DIR, sub-questions, query list, file paths). Run independent lanes in
**one message** so they execute in parallel. If your harness has registered
`xerok-research:*` agents, you may use those subagent types instead.

## When NOT to use / red flags

- "What's the capital of X?", a single doc lookup, or anything your own knowledge
  answers → answer directly, don't spin up the engine.
- The pipeline is a means, not a ritual: for a small question run `quick` (or
  skip it). Don't dispatch 16 agents for something two searches would settle.
