# XEROK — Output Contract (the hard spec)

This is the rigid format the **write** and **edit** stages must produce. The
mechanical parts are enforced by `scripts/xerok.py` (postpass + validate); the
judgment parts are your responsibility. Honoring this contract is where most of
the quality score lives — Dalpha's #1 ranking came from *presentation*, not from
finding more facts.

## 0. Invariants (never violate)

- **Language-lock.** The report is written in the **same language as the user's
  question** unless they ask otherwise. Cite sources in their original language.
- **Grounding.** Every factual claim — a number, price, spec, benchmark, date,
  named product, or quote — carries an inline `[n]` citation backed by an item in
  the evidence bank. No bank item → no claim. Never invent a source or a URL.
- **Primary sources only.** A citation must be a **deep link to a primary
  document**: vendor pricing/docs pages, GitHub repos, arXiv/PDFs, official
  benchmarks, datasheets, gov/standards permalinks. **Homepages, social posts,
  Reddit, and generic listicles are not acceptable as primary citations** (use
  them only for orientation, never as the `[n]` backing a hard claim). Target
  ≥70% primary (validate enforces this).
- **Surface conflicts, don't flatten them.** When sources disagree, present both
  with their basis ("on spot pricing X; on-demand Y"), don't silently pick one.
- **Hedge honestly.** Prefer conditional, bounded claims ("≈2× on this workload,
  vendor-reported") over absolutes. State the decision rule when you apply one.

## 1. Long report structure (standard / deep depth)

Emit sections in this order. Use `##` for top sections, `###` for sub-parts.

1. **Title** — specific; names the scope and the method/angle.
2. **Executive Summary** — 4–8 *numbered* core conclusions, key terms in **bold**.
   A reader who stops here has the answer.
3. **Scope** — two short sub-sections:
   - **What this report establishes**
   - **What it does NOT establish** (negative scoping; pre-empts overclaiming)
   - If the question has ambiguous entities, include a **disambiguation table**:
     `Requested term | Resolved canonical name | Basis/units | Coverage | Caveat`.
4. **Body sections** — one `##` per major theme from the plan. Each section is
   grounded and citation-dense (see the not-hollow gate below). Tables for
   comparisons; both sides for conflicts.
5. **Comprehensive Analysis** — answer **each sub-question 1:1, in order**, with
   `### N. <restate the sub-question>` headings. This is instruction-following
   made structural; do not skip or merge sub-questions.
6. **Limitations and Caveats** — subdivided (data freshness, measurement basis,
   sample/uncertainty, scope mismatch). Mandatory.
7. **Conclusion** — restate the conservative, conditional bottom line.
8. **Sources** — see citation contract.

## 2. Quick report structure (quick depth / "Exact Facts")

```
# <Title>

## Exact Facts / Key Findings
- **<entity/metric>**: <fact with number> [n]
- ... (scannable TL;DR, bolded entities, every line cited)

## Main Report
<3–6 tight paragraphs answering the question, grounded and cited>

## Limitations
<2–4 bullets>

## Sources
<citation block>
```

## 3. Citation contract (mechanical — postpass enforces)

- Inline marker: `[n]` immediately after the claim it backs. Reuse the same `n`
  for repeat references to one source.
- Trailing block, exactly:
  ```
  ## Sources

  [1] Publisher/Org, Descriptive Title
  https://deep-link-to-primary-document

  [2] ...
  ```
- One source per number; every `[n]` in the body resolves to a Sources entry;
  every Sources entry is referenced at least once. `xerok.py postpass`
  renumbers by appearance order and rebuilds the block; `xerok.py validate`
  fails on dangling markers and low primary-source ratio.

## 4. The not-hollow gate (per-section, write stage)

A section **fails** and must be regenerated (cap 2 retries) if any is true:
- It contains zero inline citations.
- It contains zero specific numbers / specs / named entities.
- It restates the question or the brief instead of answering with evidence.
- A `numeric_spine` value that belongs in it is missing.

A section **passes** when it carries concrete evidence (numbers/specs/entities),
every hard claim is cited to a primary source, and conflicts are surfaced.

## 5. Anti-AI-writing (prose quality)

The refiner and readability passes must avoid AI tells; postpass is the safety
net for the mechanical ones:
- Em-dash density capped (postpass `--emdash-budget`, default 2 per 1000 words).
- No "it's important to note", "in today's fast-paced world", "delve",
  "tapestry", hollow throat-clearing, or section-ending summaries that repeat the
  section.
- Vary sentence length; lead with the fact, not the meta-commentary.
- Prefer tables/lists for dense comparisons over prose walls.
