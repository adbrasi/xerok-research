#!/usr/bin/env python3
"""
XEROK RESEARCH — deterministic engine (NO LLM, idempotent, fail-soft).

One stdlib-only CLI that owns every mechanical step of the pipeline so the LLM
sub-agents never have to. Subcommands:

  init            create a run directory + state.json skeleton
  merge-evidence  dedup lane evidence, score source primacy, report coverage/gaps
  postpass        deterministic cleanup of the final report (in place, idempotent)
  metrics         article_metrics: words, citations, sources, sections, ...
  validate        check the report against the typed plan (criteria, grounding)

Design contract (SkillsBench-aligned):
  * Calibrated defaults baked in; every threshold has a flag override.
  * Fail-soft: a crashing op is skipped and logged, never aborts the run.
  * Idempotent: running postpass twice yields the same bytes.
  * Canonical data formats documented inline (evidence JSONL, state.json).

Evidence JSONL (one object per line, written by each research lane to
  <run>/evidence/<lane>.jsonl):
    {
      "claim":   "concise factual statement",          # required
      "value":   "12.3 / $0.69/hr / RTX 4090",         # optional numeric/spec
      "source_url":   "https://...",                    # required, deep link
      "source_title": "Publisher, Title",               # required
      "lane":    "evidence|mechanism|comparator|critic|horizon",
      "sub_question_ids": [1, 3],                        # which plan items it serves
      "date":    "2026-05",                              # optional recency
      "confidence": "high|medium|low"                    # optional
    }

state.json (written by `init`, enriched by the orchestrator):
    {
      "question": "...", "language": "auto", "depth": "standard",
      "sub_questions": ["...", "..."],
      "acceptance_criteria": ["regex or literal string to find in report", ...],
      "numeric_spine": ["values/specs that MUST appear in the report", ...]
    }
"""

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# ----------------------------------------------------------------------------- helpers

def _now_slug() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _log(msg: str) -> None:
    print(f"[xerok] {msg}", file=sys.stderr)


def _safe(op_name, fn, *a, **k):
    """Run an op fail-soft. Returns (ok, result_or_error)."""
    try:
        return True, fn(*a, **k)
    except Exception as e:  # noqa: BLE001 - fail-soft is the whole point
        _log(f"op '{op_name}' skipped: {e}")
        return False, str(e)


def _read_lines_json(path: Path):
    items = []
    if not path.exists():
        return items
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            items.append(json.loads(ln))
        except json.JSONDecodeError:
            _log(f"skipping malformed evidence line in {path.name}: {ln[:80]}")
    return items


# ----------------------------------------------------------------------------- source primacy

# Domains/path-shapes that signal a PRIMARY / strong source.
_STRONG_HINTS = (
    ".gov", ".gov.cn", ".mil", "arxiv.org", "github.com", "huggingface.co",
    "docs.", "/docs/", "developer.", "sec.gov", "europa.eu", "ieee.org",
    "nature.com", "acm.org", "openreview.net", ".pdf",
)
# Domains that are usually secondary/aggregator/social — flagged, not banned.
_WEAK_DOMAINS = (
    "reddit.com", "quora.com", "medium.com", "twitter.com", "x.com",
    "facebook.com", "pinterest.com", "youtube.com", "linkedin.com",
    "wikipedia.org",  # great for orientation, weak as a primary citation
)


def classify_source(url: str):
    """Return (is_primary: bool, reason: str). Heuristic, conservative."""
    try:
        p = urlparse(url.strip())
    except Exception:
        return False, "unparseable-url"
    if p.scheme not in ("http", "https") or not p.netloc:
        return False, "not-a-url"
    host = p.netloc.lower()
    path = (p.path or "/").rstrip("/")
    url_l = url.lower()

    if any(h in url_l for h in _STRONG_HINTS):
        return True, "primary-signal"
    if host.split(":")[0] in _WEAK_DOMAINS or any(host.endswith(d) for d in _WEAK_DOMAINS):
        return False, "aggregator-or-social"
    if path == "" or path == "/":
        return False, "bare-homepage"
    # A deep link on a normal domain (>= 2 path segments) is acceptable.
    if path.count("/") >= 2:
        return True, "deep-link"
    return True, "ok-shallow"


def _norm_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        host = p.netloc.lower()
        path = (p.path or "/").rstrip("/") or "/"
        return f"{host}{path}"
    except Exception:
        return url.strip().lower()


def _claim_key(claim: str) -> str:
    norm = re.sub(r"\s+", " ", (claim or "").strip().lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------------------------- init

def cmd_init(args):
    base = Path(args.dir or "xerok-runs")
    run = base / (args.id or _now_slug())
    (run / "evidence").mkdir(parents=True, exist_ok=True)
    (run / "sections").mkdir(parents=True, exist_ok=True)
    state = {
        "question": args.question,
        "language": args.lang,
        "depth": args.depth,
        "created": _now_slug(),
        "sub_questions": [],
        "acceptance_criteria": [],
        "numeric_spine": [],
    }
    state_path = run / "state.json"
    if state_path.exists() and not args.force:
        _log(f"state.json already exists at {state_path} (use --force to overwrite)")
    else:
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    # machine-readable line the orchestrator can grep
    print(str(run))
    return 0


# ----------------------------------------------------------------------------- merge-evidence

def cmd_merge_evidence(args):
    run = Path(args.run_dir)
    ev_dir = run / "evidence"
    state = {}
    sp = run / "state.json"
    if sp.exists():
        state = _safe("load-state", lambda: json.loads(sp.read_text(encoding="utf-8")))[1] or {}

    lane_files = sorted(p for p in ev_dir.glob("*.jsonl") if p.name != "bank.jsonl")
    raw = []
    for lf in lane_files:
        for it in _read_lines_json(lf):
            it.setdefault("lane", lf.stem)
            raw.append(it)

    seen = {}
    deduped = []
    for it in raw:
        url = it.get("source_url", "")
        key = (_norm_url(url), _claim_key(it.get("claim", "")))
        if key in seen:
            continue
        seen[key] = True
        primary, reason = classify_source(url)
        it["_primary"] = primary
        it["_primary_reason"] = reason
        deduped.append(it)

    bank = ev_dir / "bank.jsonl"
    bank.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in deduped) + ("\n" if deduped else ""),
        encoding="utf-8",
    )

    # coverage per sub-question
    subs = state.get("sub_questions", []) or []
    min_ev = args.min_evidence
    coverage = []
    for idx, sq in enumerate(subs, start=1):
        n = sum(1 for it in deduped if idx in (it.get("sub_question_ids") or []))
        # keyword fallback when lanes didn't tag ids
        if n == 0:
            terms = [w for w in re.findall(r"[A-Za-z0-9]{4,}", sq.lower())][:6]
            for it in deduped:
                blob = f"{it.get('claim','')} {it.get('value','')}".lower()
                if terms and sum(t in blob for t in terms) >= max(1, len(terms) // 3):
                    n += 1
        coverage.append({"sub_question": idx, "text": sq, "evidence_count": n, "gap": n < min_ev})

    n_sources = len({_norm_url(it.get("source_url", "")) for it in deduped})
    n_weak = sum(1 for it in deduped if not it["_primary"])
    report = {
        "run_dir": str(run),
        "lanes": [lf.stem for lf in lane_files],
        "evidence_total_raw": len(raw),
        "evidence_total_deduped": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "unique_sources": n_sources,
        "non_primary_evidence": n_weak,
        "non_primary_examples": [
            {"url": it.get("source_url"), "reason": it["_primary_reason"]}
            for it in deduped if not it["_primary"]
        ][:10],
        "coverage": coverage,
        "gaps": [c for c in coverage if c["gap"]],
        "bank": str(bank),
    }
    (run / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


# ----------------------------------------------------------------------------- postpass

_SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def _split_citation_and_sources(text: str):
    """Return (body, sources_header, sources_block) splitting on a Sources/References heading."""
    m = re.search(r"(?im)^#{1,6}\s*(sources|references|来源|参考文献)\s*$", text)
    if not m:
        return text, None, None
    return text[: m.start()], text[m.start(): m.end()], text[m.end():]


def op_normalize_citations(text: str):
    """Renumber inline [n] markers in order of first appearance and rebuild the
    Sources block to match. Reports dangling markers and unused sources.
    Idempotent. Only runs if a Sources block exists."""
    body, src_header, src_block = _split_citation_and_sources(text)
    if src_header is None:
        return text, {"changed": False, "note": "no-sources-block"}

    # parse existing sources: "[n] Title" possibly followed by a URL line
    entries = {}  # old_num -> {"title":..., "url":...}
    cur = None
    for ln in src_block.splitlines():
        s = ln.strip()
        m = re.match(r"^\[(\d+)\]\s*(.*)$", s)
        if m:
            cur = int(m.group(1))
            entries[cur] = {"title": m.group(2).strip(), "url": ""}
        elif s.startswith("http") and cur is not None and not entries[cur]["url"]:
            entries[cur]["url"] = s

    order = []
    for mt in re.finditer(r"\[(\d+)\]", body):
        n = int(mt.group(1))
        if n not in order:
            order.append(n)

    remap = {old: i + 1 for i, old in enumerate(order)}
    dangling = [n for n in order if n not in entries]
    unused = [n for n in entries if n not in remap]

    def _sub(mt):
        n = int(mt.group(1))
        return f"[{remap.get(n, n)}]"

    new_body = re.sub(r"\[(\d+)\]", _sub, body)

    new_src_lines = [src_header.strip(), ""]
    for old in order:
        if old in entries:
            e = entries[old]
            new_src_lines.append(f"[{remap[old]}] {e['title']}".rstrip())
            if e["url"]:
                new_src_lines.append(e["url"])
            new_src_lines.append("")
    rebuilt = new_body.rstrip() + "\n\n" + "\n".join(new_src_lines).rstrip() + "\n"
    return rebuilt, {
        "changed": rebuilt != text,
        "citations_renumbered": sum(1 for o, n in remap.items() if o != n),
        "dangling_markers": dangling,
        "unused_sources": unused,
    }


def op_clamp_emdash(text: str, budget_per_1000w: float):
    """Reduce em-dash density (an AI-writing tell) below a budget by converting
    surplus ' — ' to ', '. Conservative: leaves dashes inside code spans alone."""
    words = max(1, len(re.findall(r"\b\w+\b", text)))
    allowed = int(budget_per_1000w * words / 1000)
    # protect inline code
    codes = []
    def _stash(m):
        codes.append(m.group(0))
        return f"\x00{len(codes)-1}\x00"
    protected = re.sub(r"`[^`]*`", _stash, text)
    positions = [m.start() for m in re.finditer(r"\s—\s|\s–\s", protected)]
    surplus = max(0, len(positions) - allowed)
    if surplus > 0:
        count = {"n": 0}
        def _rep(m):
            if count["n"] < surplus:
                count["n"] += 1
                return ", "
            return m.group(0)
        protected = re.sub(r"\s—\s|\s–\s", _rep, protected)
    for i, c in enumerate(codes):
        protected = protected.replace(f"\x00{i}\x00", c)
    return protected, {"changed": protected != text, "emdash_removed": surplus, "emdash_budget": allowed}


def op_cjk_despace(text: str):
    """Remove stray ASCII spaces inserted between CJK characters / CJK punctuation."""
    cjk = r"一-鿿぀-ヿ　-〿＀-￯"
    out = re.sub(rf"([{cjk}])\s+([{cjk}])", r"\1\2", text)
    out = re.sub(rf"([{cjk}])\s+([{cjk}])", r"\1\2", out)  # second pass for runs
    return out, {"changed": out != text}


def op_normalize_whitespace(text: str):
    """Collapse 3+ blank lines, strip trailing spaces, ensure single trailing newline."""
    out = "\n".join(ln.rstrip() for ln in text.splitlines())
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.rstrip() + "\n", {"changed": True}


def op_flag_long_paragraphs(text: str, max_sentences: int):
    """FLAG-only (non-destructive): report paragraphs longer than max_sentences."""
    flagged = 0
    for para in re.split(r"\n\s*\n", text):
        p = para.strip()
        if p.startswith(("#", "-", "*", ">", "|", "```")) or re.match(r"^\d+\.", p):
            continue
        if len(_SENT_SPLIT.split(p)) > max_sentences:
            flagged += 1
    return text, {"changed": False, "long_paragraphs": flagged}


def cmd_postpass(args):
    path = Path(args.report)
    if not path.exists():
        _log(f"report not found: {path}")
        return 1
    original = path.read_text(encoding="utf-8", errors="replace")
    if not args.no_backup:
        path.with_suffix(path.suffix + ".bak").write_text(original, encoding="utf-8")

    text = original
    report = {}
    chain = [
        ("normalize_citations", lambda t: op_normalize_citations(t)),
        ("clamp_emdash", lambda t: op_clamp_emdash(t, args.emdash_budget)),
        ("cjk_despace", lambda t: op_cjk_despace(t)),
        ("flag_long_paragraphs", lambda t: op_flag_long_paragraphs(t, args.max_para_sentences)),
        ("normalize_whitespace", lambda t: op_normalize_whitespace(t)),
    ]
    for name, fn in chain:
        ok, res = _safe(name, fn, text)
        if ok:
            text, meta = res
            report[name] = meta
        else:
            report[name] = {"error": res}

    path.write_text(text, encoding="utf-8")
    report["_idempotent_note"] = "re-run yields identical bytes"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


# ----------------------------------------------------------------------------- metrics

def _count_words(text: str) -> int:
    # CJK chars count individually; latin by token
    cjk = len(re.findall(r"[一-鿿]", text))
    latin = len(re.findall(r"\b[A-Za-z0-9]+\b", text))
    return cjk + latin


def cmd_metrics(args):
    text = Path(args.report).read_text(encoding="utf-8", errors="replace")
    body, _, src_block = _split_citation_and_sources(text)
    inline = [int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", body)]
    src_nums = set()
    src_urls = set()
    if src_block:
        for ln in src_block.splitlines():
            m = re.match(r"^\s*\[(\d+)\]", ln)
            if m:
                src_nums.add(int(m.group(1)))
            if ln.strip().startswith("http"):
                src_urls.add(ln.strip())
    headings = re.findall(r"(?m)^(#{1,6})\s+\S", text)
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith(("#", "|", "```"))]
    longest = max((len(_SENT_SPLIT.split(p.strip())) for p in paras), default=0)
    out = {
        "words": _count_words(text),
        "headings": len(headings),
        "sections_h2": len(re.findall(r"(?m)^##\s+\S", text)),
        "inline_citations": len(inline),
        "unique_inline_citations": len(set(inline)),
        "sources_listed": len(src_nums),
        "source_urls": len(src_urls),
        "citations_without_source": sorted(set(inline) - src_nums),
        "sources_without_citation": sorted(src_nums - set(inline)),
        "em_dashes": len(re.findall(r"\s—\s|\s–\s", body)),
        "longest_paragraph_sentences": longest,
        "mermaid_blocks": len(re.findall(r"```mermaid", text)),
        "has_sources_block": src_block is not None,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ----------------------------------------------------------------------------- validate

def cmd_validate(args):
    run = Path(args.run_dir)
    state = json.loads((run / "state.json").read_text(encoding="utf-8")) if (run / "state.json").exists() else {}
    text = Path(args.report).read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    body, _, src_block = _split_citation_and_sources(text)

    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    # 1. every inline citation resolves
    inline = set(int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", body))
    src_nums = set()
    if src_block:
        for ln in src_block.splitlines():
            m = re.match(r"^\s*\[(\d+)\]", ln)
            if m:
                src_nums.add(int(m.group(1)))
    dangling = sorted(inline - src_nums)
    add("citations_resolve", not dangling, f"dangling={dangling}")

    # 2. primary-source ratio
    urls = re.findall(r"https?://\S+", src_block or "")
    if urls:
        weak = [u for u in urls if not classify_source(u)[0]]
        ratio = 1 - len(weak) / len(urls)
        add("primary_source_ratio", ratio >= args.min_primary_ratio,
            f"{ratio:.2f} primary ({len(weak)} weak of {len(urls)})")
    else:
        add("primary_source_ratio", False, "no source urls found")

    # 3. limitations / caveats section present
    add("limitations_section",
        bool(re.search(r"(?im)^#{1,6}.*(limitation|caveat|局限|不确定)", text)),
        "")

    # 4. each sub-question addressed (key-term match)
    subs = state.get("sub_questions", []) or []
    missed = []
    for idx, sq in enumerate(subs, start=1):
        terms = [w for w in re.findall(r"[A-Za-z0-9]{4,}", sq.lower())][:6]
        hit = sum(t in low for t in terms)
        if terms and hit < max(1, len(terms) // 2):
            missed.append(idx)
    add("sub_questions_covered", not missed, f"missed={missed} of {len(subs)}")

    # 5. numeric spine present
    spine = state.get("numeric_spine", []) or []
    miss_spine = [v for v in spine if v and v.lower() not in low]
    add("numeric_spine_present", not miss_spine, f"missing={miss_spine[:8]}")

    # 6. acceptance criteria (literal or regex) found
    crit = state.get("acceptance_criteria", []) or []
    miss_crit = []
    for c in crit:
        try:
            if not re.search(c, text, re.IGNORECASE):
                miss_crit.append(c)
        except re.error:
            if c.lower() not in low:
                miss_crit.append(c)
    add("acceptance_criteria_met", not miss_crit, f"missing={miss_crit[:8]}")

    overall = all(c["pass"] for c in checks)
    result = {"overall_pass": overall, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if overall else 2


# ----------------------------------------------------------------------------- cli

def main(argv=None):
    p = argparse.ArgumentParser(prog="xerok", description="XEROK RESEARCH deterministic engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="create a run directory + state.json")
    pi.add_argument("question")
    pi.add_argument("--dir", default="xerok-runs")
    pi.add_argument("--id", default="")
    pi.add_argument("--depth", default="standard", choices=["quick", "standard", "deep"])
    pi.add_argument("--lang", default="auto")
    pi.add_argument("--force", action="store_true")
    pi.set_defaults(func=cmd_init)

    pm = sub.add_parser("merge-evidence", help="dedup + score sources + coverage report")
    pm.add_argument("run_dir")
    pm.add_argument("--min-evidence", type=int, default=2, dest="min_evidence")
    pm.set_defaults(func=cmd_merge_evidence)

    pp = sub.add_parser("postpass", help="deterministic in-place cleanup of the report")
    pp.add_argument("report")
    pp.add_argument("--emdash-budget", type=float, default=2.0, dest="emdash_budget",
                    help="max em-dashes per 1000 words (default 2.0)")
    pp.add_argument("--max-para-sentences", type=int, default=6, dest="max_para_sentences")
    pp.add_argument("--no-backup", action="store_true")
    pp.set_defaults(func=cmd_postpass)

    pme = sub.add_parser("metrics", help="article metrics as JSON")
    pme.add_argument("report")
    pme.set_defaults(func=cmd_metrics)

    pv = sub.add_parser("validate", help="check report against the typed plan")
    pv.add_argument("run_dir")
    pv.add_argument("report")
    pv.add_argument("--min-primary-ratio", type=float, default=0.7, dest="min_primary_ratio")
    pv.set_defaults(func=cmd_validate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
