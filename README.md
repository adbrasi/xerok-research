# XEROK RESEARCH

A Claude Code **plugin/skill** that runs an advanced, multi-agent **deep-research
engine**: one question → a primary-source-**cited report**, through four stages —
**Plan → Research → Write → Edit**.

It is the orchestration playbook from "THE ENGINE" flow (typed state object handed
through plan/research/write/edit, five isolated-context research specialists in
parallel, a per-section quality loop, and a deterministic post-pass chain),
adapted to Claude Code and to **opus + sonnet** sub-agents.

## What it does

- **Plan** — scopes the question into a *typed plan*: sub-questions, 6–64 research
  queries (by depth), acceptance criteria the engine can later check, an entity
  disambiguation table, and the numeric "spine" the report must surface.
- **Research** — fans out up to **5 parallel specialists** with isolated context
  (`evidence`, `mechanism`, `comparator`, `critic`, `horizon`), each writing
  strict-schema evidence to files. A deterministic step dedups the evidence,
  scores **source primacy** (flags homepages/social), and reports coverage/gaps,
  driving an evidence-sufficiency gap-fill loop.
- **Write** — builds the report section by section, grounded in the evidence
  bank, with a per-section **grounding → score → regen** quality loop and a
  *not-hollow* gate.
- **Edit** — a refiner + readability pass, then a **deterministic post-pass**
  (NO LLM, idempotent, fail-soft): citation renumber/dedup, Sources rebuild,
  em-dash clamp, CJK despace, whitespace normalize — then **validation** against
  the plan (citations resolve, ≥70% primary sources, sub-questions answered 1:1,
  limitations present, acceptance criteria met).

## Design sources

- **THE ENGINE** four-stage flow (the reference diagram) — the backbone.
- **Dalpha-DeepResearch** (DeepResearch Bench II #1) — its edge was *presentation*
  (93.41): a hard output contract enforced by a separate edit pass, primary-source
  -only citations, mandatory negative-scoping + limitations sections, and a
  "Comprehensive Analysis" that answers each sub-question 1:1. All adopted here.
- **SkillsBench** guidance — concise over exhaustive; ship an **executable script
  with calibrated defaults** (`scripts/xerok.py`); document canonical data formats
  and parsing quirks; codify the exact format/invariants the validator checks; a
  direct frontmatter description; and an explicit **Complexity Contract** (cost,
  applicability limits, lightweight fast-path fallback).

## Layout

```
.claude-plugin/plugin.json          # plugin manifest
skills/xerok-research/
  SKILL.md                          # orchestrator playbook (loaded on invoke)
  references/output-contract.md     # the hard report/citation spec
  references/specialists.md         # role prompts pasted into sub-agent dispatches
  scripts/xerok.py                  # deterministic engine (stdlib only)
docs/TECHNICAL_BRIEFING.md          # Claude Code skills/plugins/subagents reference
```

## Install

Skill-directory plugin (auto-loaded, no marketplace):

```bash
ln -s "$(pwd)" ~/.claude/skills/xerok-research      # or copy the folder
```

Or run Claude Code with the plugin dir directly:

```bash
claude --plugin-dir /home/adolfocesar/projects/deep_research
```

Then invoke with `/xerok-research:xerok-research` (or just ask for "deep research
on …" and let Claude pick it up).

## Use the engine directly

```bash
SCRIPT=skills/xerok-research/scripts/xerok.py
RUN=$(python3 $SCRIPT init "your question" --depth deep)   # -> run dir
#   ... sub-agents fill $RUN/evidence/<lane>.jsonl ...
python3 $SCRIPT merge-evidence "$RUN"                       # dedup + coverage
python3 $SCRIPT postpass  "$RUN/report.md"                  # deterministic cleanup
python3 $SCRIPT metrics   "$RUN/report.md"                  # article metrics
python3 $SCRIPT validate  "$RUN" "$RUN/report.md"           # check vs the plan
```

Requires Python 3.8+ (standard library only — no dependencies).
