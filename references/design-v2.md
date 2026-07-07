# AnySearch Payload Control — Final Design (v2)

> Supersedes the original design (design-v1). This document is the single
> source of truth for the `--format` payload-control feature. Implementation
> target: anysearch.py v2.

---

## 0. Problem Statement

The CLI today returns **full content** for every search result. Each result is
a Markdown text blob (title + URL + full page content) embedded in the JSON-RPC
`content` array. There are no structured `title` / `url` / `score` fields.

Cost in practice: `batch_search` 5 queries × 10 results ≈ 70 KB / ~20 K tokens
of context per call — most of it noise when the Agent only needs to *discover*
which pages are worth reading.

**Goal:** add a client-side resolution knob so the Agent pays only for the
tokens it needs at each step of the search → extract pipeline.

---

## 1. Mental Model

Search is **discovery** (which pages are worth reading?). Extract is
**deep-read** (what does *this* page say?). The format knob lets the Agent
choose how much of each result to materialize into context:

| Resolution | Role in the pipeline | Rough cost |
|---|---|---|
| `compact` | Discovery — scan titles + URLs, pick winners | ~90 B/条 |
| `snippet` | Evaluation — peek at leading content to confirm relevance | ~550 B/条 |
| `full` | Deep-read (or quick single-shot answer) | ~2 KB+/条 |

The two-step flow `search --format compact` → `extract <URL>` is the default
mental model. The one-shot `search --format full --max-results 1` escape hatch
exists for when the Agent already knows the top hit is what it needs.

---

## 2. Review Feedback — Point-by-Point Disposition

| # | Feedback | Disposition | Rationale |
|---|---|---|---|
| 1 | snippet is positional truncation, not semantic excerpt | **Adopt (mitigate + document)** | We cannot do API-side semantic highlighting (the API returns one text blob). v1 ships positional truncation **with lead-noise skipping** (§5.3) and a prominent SKILL.md note that snippet is positional, not semantic. A future `--format highlights` that calls an LLM/summarizer is deferred to v2. |
| 2 | Default compact is correct, but every SKILL.md example must show `--format`; add a "quick answer" escape hatch | **Adopt fully** | Discoverability of the knob is the single biggest adoption lever. §6 decision table and §7 examples always show `--format`, and the escape-hatch row is added. |
| 3 | batch dedup: full should dedup too; add `--no-dedup`; canonicalize scheme + www | **Adopt fully** | The "full doesn't dedup" rule was over-engineering. Unified: **default dedup across all formats**, `--no-dedup` to opt out. Canonicalization now normalizes `http→https` and strips `www.` (§5.4). |
| 4 | Metadata header should use exact post-output size; hint only on compact/snippet and only once | **Adopt fully** | The tool knows the rendered output size after building it — emit the exact byte count. The `→ extract` hint appears only when at least one result is rendered in compact/snippet, and only once at the very end. `full` mode omits the hint (the Agent already has the content). |
| 5 | help is a reference manual, not the decision entry; keep help ↔ decision table consistent | **Adopt fully** | §4 help text is the mechanical reference; §6 SKILL.md decision table is the decision surface. They share the same `--format` vocabulary and defaults. Any change to one must update the other. |
| 6 | Missing optimization dimensions: score filter (high), domain filter (med), time range (med) | **Adopt score as v1, defer domain/time to v2** | The API does not return a numeric score, but **rank position** is an implicit score (result #1 > #5). v1 shows `#1`..`#N` rank in compact/snippet output so the Agent has a relevance signal. `--include-domains` / `--exclude-domains` and `--after YYYY-MM-DD` are deferred to v2 (§8). |
| 7 | Over-engineering: batch per-format dedup strategy is too complex | **Adopt fully** | Removed. Single rule: default dedup, `--no-dedup` to disable. Applies to `search` (trivially, single query) and `batch_search` uniformly. |
| 8 | Decision table needs the escape-hatch row + 2–3 end-to-end examples | **Adopt fully** | §6 adds the "Quick answer" row; §7 provides three worked examples. |
| 9 | extract should also support `--format` | **Adopt fully** | `extract` gains `--format {compact,snippet,full}` (default `full`). compact/snippet on extract are useful when the Agent wants to verify a URL before committing the full page to context. See §5.5. |
| 10 | Clarify: format is client-side; network payload is unchanged | **Adopt fully** | §3 states explicitly that the API always returns full content; the tool truncates at render time. Network cost is unchanged; only context-token cost drops. |
| 11 | compact mode score display — use rank as implicit score | **Adopt fully** | See #6. Compact/snippet output prefixes each result with `#N` rank. |
| 12 | Format discoverability: append a one-line hint at the end of compact output | **Adopt fully** | §5.2: compact output ends with `(use --format snippet for content previews, --format full for complete content)`. snippet ends with `(use --format full for complete content, or extract <URL> to deep-read one page)`. `full` has no hint. The hint appears once, at the very end. |

### Rejected / not adopted

None. Every review point was adopted, either fully or with a v1/v2 split.

---

## 3. Architecture: Client-Side Truncation

```
  Agent CLI invocation
        │
        ▼
  AnySearch API  ──► JSON-RPC response (content[].text = full Markdown blob)
        │                 ▲
        │                 │  network payload = FULL (unchanged)
        ▼
  _render_results()  ──►  truncates / restructures per --format
        │
        ▼
  stdout  ──► Agent context  (only what --format allows)
```

**Important:** `--format` reduces **context-token cost**, not network cost.
The API still returns the full blob. This is the same trade-off Tavily makes
when `include_raw_content=false` — except we do the trimming client-side
because the AnySearch API has no server-side trim parameter.

**Implication for large pages:** if the API itself is slow on huge pages,
`--format compact` will *not* speed up the network round-trip — it only saves
the Agent's context budget. This is documented in the help text.

---

## 4. Parameter Design & Help Text

### 4.1 `search` subcommand

```
usage: anysearch search [-h] [--domain DOMAIN] [--sub_domain SUB_DOMAIN]
                        [--sdp SDP] [--max_results N] [--format FORMAT]
                        [--max-chars N] [--no-dedup]
                        query

positional arguments:
  query

options:
  --domain, -d          Vertical domain (e.g. finance, code). Omit for general.
  --sub_domain, -s      Sub-domain (from get_sub_domains output).
  --sdp, -p             Sub-domain params: key=val,key=val  OR  JSON string.
  --max_results, -m N   Max results to request from API. Default 5, max 10.
  --format              compact | snippet | full. Default: compact.
                        compact = title + URL + rank only (~90 B).
                        snippet = title + URL + rank + first N chars (~550 B).
                        full    = complete content (~2 KB+).
                        The API always returns full content; the tool trims
                        at render time. Network payload is unchanged.
  --max-chars N         Char budget for snippet mode. Default 500. Ignored
                        by compact and full.
  --no-dedup            Disable cross-result URL dedup (default: dedup on).
```

### 4.2 `batch_search` subcommand

```
usage: anysearch batch_search [-h] [--query Q] [--domain DOMAIN]
                              [--sub_domain SUB_DOMAIN] [--sdp SDP]
                              [--max_results N] [--format FORMAT]
                              [--max-chars N] [--no-dedup]
                              [queries]

positional arguments:
  queries               JSON array of query objects.

options:
  --query Q             Repeatable: one --query per query (max 5).
  --domain, -d          Applied to queries that don't set their own domain.
  --sub_domain, -s      Applied to queries that don't set their own sub_domain.
  --sdp, -p             Applied to queries that don't set their own sdp.
  --max_results, -m N   Applied to each query. Default 5, max 10.
  --format              compact (default) | snippet | full.
  --max-chars N         Char budget for snippet. Default 500.
  --no-dedup            Disable cross-query URL dedup (default: dedup on).
                        Dedup is cross-query: the same URL appearing in two
                        query results is kept only on its first occurrence.
```

### 4.3 `extract` subcommand

```
usage: anysearch extract [-h] [--format FORMAT] [--max-chars N]
                         url

positional arguments:
  url

options:
  --format              compact | snippet | full. Default: full.
                        compact = title + URL + rank (for extract, rank is
                        always #1 since it's a single page).
                        snippet = first N chars of the extracted page.
                        full    = complete extracted page (default).
  --max-chars N         Char budget for snippet. Default 500.
```

### 4.4 Why `compact` is the default for search but `full` for extract

- **search** default `compact`: the dominant use case is discovery; the Agent
  should not pay 2 KB per candidate it may discard. The escape hatch
  (`--format full --max-results 1`) covers the known-single-hit case.
- **extract** default `full`: extract is the *deep-read* step — the Agent
  already chose to read this page. Defaulting to snippet would defeat the
  purpose. compact/snippet on extract are for the rare "verify before commit"
  case.

---

## 5. Output Format Design

### 5.1 Parsing the API blob

Each search result `content[].text` is a Markdown blob. Empirically it begins
with a title line and a URL line, followed by page content:

```
# Page Title
https://example.com/page

<body text ...>
```

The parser extracts:
- `title`  = first `# `-prefixed line (or first non-empty line if no heading).
- `url`    = first line matching `^https?://`.
- `body`   = everything after the URL line.

If the blob doesn't match this shape (no URL line), the whole text is treated
as `body` and `title`/`url` are empty strings. This graceful fallback prevents
a format change in the API from breaking rendering.

### 5.2 Rendering by format

#### compact

```
#N  Title
    https://url
```

One blank line between results. After all results:

```
(use --format snippet for content previews, --format full for complete content)
```

The hint line is **only** appended in compact mode, **only once**, at the very
end.

#### snippet

```
#N  Title
    https://url
    <first N chars of body, with lead noise skipped>
```

After all results:

```
(use --format full for complete content, or extract <top-URL> to deep-read one page)
```

The hint is appended **only once** at the end. The `<top-URL>` is the URL of
the first rendered result, as a concrete suggestion.

#### full

Renders the original blob as-is (title + URL + full body). **No hint line** —
the Agent already has everything.

### 5.3 Lead-noise skipping (snippet mode)

Before taking the first `N` chars of `body`, skip a bounded amount of leading
noise:

1. Strip leading whitespace.
2. Skip up to **200 chars** of leading lines that match a noise heuristic:
   - lines shorter than 40 chars AND containing navigation/ad patterns:
     `menu`, `skip to`, `sign in`, `log in`, `subscribe`, `cookie`, `advertis`,
     `javascript`, `©`, `home`, `about`, `contact`, `search`, `nav`, `button`.
   - empty lines.
3. If after skipping 200 chars nothing remains, fall back to the original
   body start (don't return an empty snippet).
4. Take the next `N` chars from the first non-noise line onward.

This is deliberately conservative — it only skips *obvious* boilerplate. The
SKILL.md note (§6) reminds the Agent that snippet is positional, not semantic:
for pages where the lead is signal (docs, papers), snippet is reliable; for
blog/news with heavy chrome, the Agent should confirm with `extract`.

### 5.4 URL deduplication & canonicalization

Applies to `search` and `batch_search` when `--no-dedup` is **not** set.

Canonicalization (for dedup key only — the displayed URL is unchanged):

1. Lowercase scheme: `HTTP://` → `http://`.
2. Normalize scheme: `http://` → `https://`.
3. Strip leading `www.` from host.
4. Remove trailing slash on path root (`/`).
5. Drop fragment (`#...`).
6. Sort query parameters alphabetically.

Two URLs that canonicalize to the same key are treated as duplicates. The
**first** occurrence (by original API order) is kept; later duplicates are
dropped and counted in the metadata header (`dedup: 3 removed`).

### 5.5 `extract` with `--format`

`extract` returns a single page. The formats:

- **compact** — `#1  <title>\n    <url>` plus the trailer hint. Useful for
  "I extracted this URL — confirm it's what I expected before committing."
- **snippet** — `#1  <title>\n    <url>\n    <first N chars>` plus the trailer
  hint. Useful for "give me the lead of this page to decide if it's worth
  reading fully."
- **full** (default) — the complete extracted Markdown. No hint.

Because extract is a single page, dedup is irrelevant and `--no-dedup` is not
accepted by the extract subcommand.

### 5.6 Metadata header (exact size)

The header is emitted as the **first** line of output, *after* the full output
text is built, so the byte count is exact:

```
## "query" — 5 results (3 deduped), 1.7s, compact, 0.42 KB
```

For `batch_search`, the query field shows the count of queries and the
combined result count:

```
## batch(3 queries) — 12 results (2 deduped), 4.1s, snippet, 6.8 KB
```

For `extract`:

```
## extract "https://..." — 1 page, 2.3s, full, 18.4 KB
```

Fields:
- `query` / `batch(N queries)` / `extract "url"` — what was asked.
- `N results (M deduped)` — results actually rendered, after dedup. If
  `--no-dedup` was set, the `(M deduped)` parenthetical is omitted.
- `T.Ts` — wall-clock elapsed, measured around the API call + render.
- `compact|snippet|full` — the format used.
- `X.XX KB` — **exact** rendered output size (the body after the header line),
  measured in UTF-8 bytes, converted to KB with 2 decimals. This is the
  number the Agent should care about for context budgeting.

The header is plain text (no ANSI) so it survives copy-paste into context.

---

## 6. SKILL.md Decision Table

This table is the **decision surface** for the Agent. It replaces prose
guesswork with a lookup. The help text (§4) is the mechanical reference.

### When to use which format

| Agent is... | `--format` | `--max-results` | Then... |
|---|---|---|---|
| **Exploring**: "what exists on X?" | `compact` (default) | 5–10 | scan titles → `extract <URL>` for the winners |
| **Evaluating**: "is this result relevant?" | `snippet` | 3–5 | if confirmed → `extract <URL>`; if not → re-search |
| **Deep-reading**: "I need all content from search" | `full` | 1–3 | done (results are full pages) |
| **Comparing**: "N aspects of X" | `compact` (batch_search) | 5/query | extract the distinct winners |
| **Quick answer**: "I know the top hit is enough" | `full` | `1` | done — one result, full content, no second call |

### Notes the Agent must internalize

1. **`snippet` is positional, not semantic.** It returns the first `N` chars
   of the page body (after skipping obvious nav/ad boilerplate). For
   documentation, papers, and reference pages the lead is usually the signal.
   For blogs, news, and pages with heavy chrome, the lead may still be noisy —
   confirm with `extract` before committing.
2. **`--format` is a client-side trim.** The API always returns full content;
   the tool renders only what `--format` allows. Network payload is unchanged
   — this knob saves your *context budget*, not your network latency.
3. **Default dedup is on.** `search` and `batch_search` dedup by canonicalized
   URL across all results. Use `--no-dedup` only when you explicitly need
   near-duplicate pages (e.g. comparing two articles on the same URL across
   time — rare).
4. **Rank is your relevance signal.** The API returns no numeric score. The
   `#N` prefix on each result is the API's implicit ranking — `#1` is the most
   relevant. Use it to decide which URLs to `extract`.
5. **`extract` defaults to `full`.** That's intentional — you already chose to
   read this page. Use `extract --format snippet` only to verify a URL before
   committing the full page to context.

### Escape hatch

```bash
# One-shot answer: top hit, full content, no second call
<cmd> search "what is the capital of France" --format full --max-results 1
```

This is the cheapest path to a single definitive answer. Use it when the query
is simple and you trust the top result.

---

## 7. End-to-End Examples

### Example 1: Exploring a topic (two-step flow)

Goal: find out what's new in WebGPU.

```bash
# Step 1 — discovery: scan titles
<cmd> search "WebGPU browser support 2025" --format compact --max-results 8
```

Output:
```
## "WebGPU browser support 2025" — 8 results, 1.4s, compact, 0.71 KB

#1  WebGPU — Wikipedia
    https://en.wikipedia.org/wiki/WebGPU
#2  Chrome WebGPU documentation
    https://developer.chrome.com/docs/webgpu
#3  State of WebGPU 2025
    https://webkit.org/blog/webgpu-2025
#4  MDN WebGPU API
    https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API
#5  WebGPU compute shaders guide
    https://gpuweb.github.io/gpuweb/wgsl
#6  Firefox WebGPU status
    https://developer.mozilla.org/en-US/docs/Mozilla/WebGPU
#7  Safari WebGPU implementation notes
    https://webkit.org/blog/webgpu-notes
#8  WebGPU performance benchmarks 2025
    https://browserbench.org/webgpu-2025

(use --format snippet for content previews, --format full for complete content)
```

Agent decides #2 and #4 look most authoritative:

```bash
# Step 2 — deep-read the winners
<cmd> extract "https://developer.chrome.com/docs/webgpu"
<cmd> extract "https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API"
```

Total context cost: 0.71 KB (discovery) + 2 × full pages — vs. the old
default of 8 × ~2 KB = ~16 KB of mostly-irrelevant full pages.

### Example 2: Batch comparison across verticals

Goal: compare quantitative easing definition vs. Fed funds rate current value.

```bash
<cmd> batch_search \
  --query "what is quantitative easing" \
  --query "Fed funds rate 2025" \
  --domain finance \
  --format compact \
  --max-results 5
```

Note: `batch_search --max-results N` applies the same cap to each query in v1.
Per-query caps are deferred to v2. `--format compact` + dedup keeps the output
small.

Output:
```
## batch(2 queries) — 9 results (1 deduped), 3.2s, compact, 0.82 KB

#1  Quantitative easing explained
    https://investopedia.com/quantitative-easing
#2  Federal Reserve funds rate
    https://federalreserve.gov/funds-rate
...

(use --format snippet for content previews, --format full for complete content)
```

Agent extracts the top hit from each query topic.

### Example 3: Quick answer (escape hatch)

Goal: single factual lookup, Agent trusts the top hit.

```bash
<cmd> search "current US inflation rate 2025" --format full --max-results 1
```

Output:
```
## "current US inflation rate 2025" — 1 result, 0.9s, full, 2.31 KB

#1  US Inflation Rate
    https://www.bls.gov/cpi

## US Inflation Rate
The current US inflation rate ... [full page content] ...
```

One call, one result, full content. No second `extract` needed.

---

## 8. v1 vs v2 Scope

### v1 — implement now

| Feature | Detail |
|---|---|
| `--format {compact,snippet,full}` | on `search`, `batch_search`, `extract` |
| `--max-chars N` | snippet char budget, default 500 |
| `--max-results N` | search and batch_search, default 5, max 10 |
| Default `compact` for search, `full` for extract | §4.4 rationale |
| Lead-noise skipping in snippet | §5.3, conservative heuristic |
| URL canonicalization + dedup | §5.4, default on, `--no-dedup` to disable |
| Exact-size metadata header | §5.6, post-render byte count |
| Rank prefix `#N` on every result | implicit score (feedback #6/#11) |
| End-of-output format hint | compact/snippet only, once, §5.2 |
| SKILL.md decision table + escape hatch + examples | §6, §7 |

### v2 — future

| Feature | Detail | Why deferred |
|---|---|---|
| `--include-domains` / `--exclude-domains` | Domain allow/deny list filter | Useful but adds arg parsing + filtering logic; not blocking the core payload-control goal. |
| `--after YYYY-MM-DD` | Time-range filter | Requires date extraction from the blob (unreliable) or an API param (not yet available). |
| `--format highlights` | Semantic key-sentence extraction (à la Exa) | Requires an LLM call or a local summarizer; significant new dependency. Keep positional snippet for now, document the limitation. |
| Per-query `--max-results` in batch_search | Let each query in a batch specify its own result count | Adds sub-structure to the `--query` flag; can be done via JSON `queries` input in v2. |
| `--format summary` | LLM-generated one-paragraph summary per result | Same dependency concern as highlights. |

---

## 9. Implementation Notes (for the engineer)

### 9.1 Where the changes go in anysearch.py

1. **`_parse_blob(text)`** — new function. Returns `(title, url, body)`.
   Called by the renderer for every result.
2. **`_canonical_url(url)`** — new function. Returns the dedup key.
3. **`_skip_lead_noise(body, budget=200)`** — new function. Returns the body
   with leading noise lines stripped, up to `budget` chars.
4. **`_render_results(results, fmt, max_chars, mode)`** — new function.
   Replaces the current `_format_result` for search/batch_search. Builds the
   output string, measures its byte length, prepends the metadata header,
   appends the format hint (if applicable).
5. **`_render_extract(blob, fmt, max_chars)`** — new function for extract.
6. **argparse** — add `--format`, `--max-chars`, `--no-dedup` to `search`,
   `batch_search`, and `extract` subparsers per §4. Add `--max-results` alias
   to search and batch_search.
7. **`_dispatch`** — after getting the API response, route to the new
   renderers instead of printing raw `_format_result` output.

### 9.2 Backward compatibility

- Calls without `--format` get `compact` (search/batch) or `full` (extract).
  This is a **behavior change** for search/batch (was full, now compact).
  This is intentional and is the entire point of the feature. The SKILL.md
  decision table makes the new default explicit.
- `--max_results` (underscore) remains the existing flag name; `--max-results`
  (hyphen) is added as an alias for consistency with `--max-chars` and
  `--no-dedup`. Both work.
- `--no-dedup` is new; its absence means dedup is on. Existing calls that
  relied on duplicate results appearing will see them deduped — this is
  desirable (feedback #3/#7).

### 9.3 Testing checklist

- [ ] compact output has no body text, only `#N  title\n    url`.
- [ ] snippet output has body truncated to `--max-chars`, noise skipped.
- [ ] full output is byte-identical to the old behavior (no trimming).
- [ ] metadata header byte count matches `wc -c` of the body.
- [ ] dedup removes cross-query duplicates in batch_search.
- [ ] `--no-dedup` preserves duplicates.
- [ ] canonicalization treats `http://www.x.com/` and `https://x.com` as same.
- [ ] extract `--format compact` renders title+url only.
- [ ] extract `--format snippet` renders first N chars.
- [ ] extract default (`full`) unchanged from old behavior.
- [ ] format hint appears once, only in compact/snippet, not in full.
- [ ] rank `#N` appears in compact and snippet, monotonically increasing.

---

## 10. Summary of Changes from v1 Design

| Area | v1 (original) | v2 (this document) |
|---|---|---|
| Default format (search) | compact | compact (unchanged) |
| Default format (extract) | (not specified) | **full** (explicit) |
| Dedup strategy | compact/snippet dedup, full no dedup | **unified: always dedup, `--no-dedup` to disable** |
| URL canonicalization | URL only | **+ scheme (http→https) + www stripping + query sort** |
| Metadata size | estimate (~0.4 KB) | **exact, post-render byte count** |
| Format hint | not specified | **compact & snippet only, once, at end** |
| Rank/score display | not in v1 | **`#N` rank prefix on every result** |
| extract `--format` | not in v1 | **added: compact/snippet/full** |
| Lead-noise skipping | not in v1 | **added (§5.3), conservative** |
| SKILL.md examples | some without `--format` | **all examples show `--format`** |
| Escape hatch | not in v1 | **`full --max-results 1` row + example** |
| Domain/time filters | implied | **explicitly deferred to v2** |
| Client-side clarification | implicit | **explicit (§3, §6 note 2)** |

---

*End of design-v2.md. Implementation should reference this document as the
specification; any deviation must be documented here first.*