---
name: anysearch
description: >-
  Probe the web with AnySearch when the agent needs external facts, current
  information, source discovery, vertical search, parallel comparison, or URL
  extraction. Use for look up, search, research, verify, investigate, gather
  sources, news, prices, papers, code, people, companies, products, places,
  events, documentation, and knowledge not already in context. Defaults to a
  light probe with compact results, then escalates to snippet/full extraction
  only when the task needs more evidence. Includes key-pool rotation and
  auto-register bootstrap when anonymous/keyed access stops working.
---

# anysearch

**Probe lightly, then extract deliberately.**

AnySearch has four primitives:

- `search` — discover candidate URLs for one query.
- `batch_search` — discover candidates across 2–5 angles, deduped by URL.
- `extract` — deep-read one selected URL.
- `get_sub_domains` — discover live vertical schemas before structured search.

`<cmd>` = `python3 <skill-dir>/scripts/anysearch.py`.

## Effort ladder

Default to the lightest probe that can answer the user. Escalate only when the
previous rung cannot satisfy the task.

| User need | Rung | Do | Completion |
|---|---|---|---|
| Quick lookup, sanity check, “what exists?” | **Light probe** | `search --format compact --max-results 5` | Titles/URLs answer the need, or useful candidates are visible. |
| Answer needs evidence or source choice | **Standard probe** | `search --format compact --max-results 8` → `extract` 1–3 winners | Answer is grounded in selected sources, not raw search noise. |
| Relevance is unclear before reading | **Sample probe** | `search --format snippet --max-results 3 --max-chars 500` | Candidate relevance is clear enough to pick winners or stop. |
| Comparison, landscape, strategy, multi-angle research | **Deep probe** | `batch_search` with 3–5 queries, `--format compact --max-results 5` → extract 3–5 distinct winners | Distinct angles are covered; repeated URLs are not re-read. |
| Ticker, DOI, CVE, package/code, flight, legal/medical/finance identifier | **Vertical probe** | `get_sub_domains` → `search --domain ... --sub_domain ... --sdp ...` | Required params came from live schema, not guessing. |
| User asks for one top answer and accepts narrow evidence | **Quick full** | `search --format full --max-results 1` | Top result is enough; do not broaden unless it looks wrong. |

Upgrade rules:

1. Start with **Light** unless the prompt clearly asks for comparison, deep research, or a vertical identifier.
2. Move from compact → snippet → full only when needed; `full` is never the default discovery mode.
3. Use `extract` only after choosing URLs from search output.
4. Use `batch_search` when one query would bias the answer or the user asks for tradeoffs, strategy, trends, competitors, or “what do people think?”.
5. For vertical search, never invent `sub_domain` or `sub_domain_params`; call `get_sub_domains` live.

## Payload modes

| Format | Output | Use |
|---|---|---|
| `compact` | `#N`, title, URL | First-pass discovery; safest for context. |
| `snippet` | compact + first `--max-chars` chars | Judge relevance before extraction. |
| `full` | complete API text | Top-hit answer or selected source only. |

Notes:

- `snippet` is positional, not semantic. It skips obvious nav/ad lead noise, then truncates.
- `--format` trims client-side: it saves **agent context**, not network latency.
- Search and batch dedup by canonical URL by default. Use `--no-dedup` only when duplicates matter.
- `#N` rank is the relevance signal; AnySearch does not expose a numeric score.
- `extract` defaults to `--format full` because a URL has already been selected; use `extract --format snippet` for cheap confirmation.

## Commands

```bash
# Light probe
<cmd> search "Cloudflare Workers 2026" --format compact --max-results 5

# Standard probe: discover, then read selected winners
<cmd> search "WebGPU browser support 2025" --format compact --max-results 8
<cmd> extract "https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API"

# Sample probe
<cmd> search "Rust async runtime comparison" --format snippet --max-results 4 --max-chars 400

# Quick full
<cmd> search "current US inflation rate 2025" --format full --max-results 1

# Deep probe
<cmd> batch_search \
  --query "Cloudflare Workers deployment" \
  --query "Cloudflare Workers observability" \
  --query "Cloudflare Workers pricing" \
  --format compact --max-results 5

# Vertical probe: schema first, then search with confirmed params
<cmd> get_sub_domains --domains finance,code
<cmd> search "AAPL" --domain finance --sub_domain finance.quote \
  --sdp type=stock,symbol=AAPL,cn_code= --format compact --max-results 3
```

Options:

- `--format compact|snippet|full` — search/batch default `compact`; extract default `full`.
- `--max-results N` / `--max_results N` / `-m N` — cap results, max 10.
- `--max-chars N` — snippet char budget, default 500.
- `--no-dedup` — disable URL dedup for search/batch.
- `--domain`, `--sub_domain`, `--sdp` — vertical search controls; call `get_sub_domains` first.

`--sdp` accepts `key=value` pairs or JSON. Params marked required must all be
passed; if a value is N/A, pass empty string (`key=`).

## Key bootstrap

Anonymous access works with lower limits. Key pool state lives in
`keys-state.json` next to `SKILL.md` and is intentionally not committed.

The skill should remain usable without manual setup:

1. On normal calls, use the existing pool automatically.
2. If keys are exhausted, invalid, rate-limited, or absent, the script can auto-register a fresh AnySearch account/key and add it to the pool.
3. If a call fails because access is unavailable, run `register` once, then retry the original probe.

```bash
# Inspect state without revealing full keys
<cmd> keys status
<cmd> keys list

# Seed or expand the pool
<cmd> register                 # create 1 account+key and add it
<cmd> register -n 5            # create 5 accounts+keys

# Make unattended recovery persistent
<cmd> keys config --auto_register true
<cmd> keys config --rotation fallback       # default: key1 until exhausted → key2
<cmd> keys config --rotation round-robin    # spread calls across active keys

# One-shot recovery for a single call
<cmd> --auto_register search "query" --format compact
```

Agent rule: when AnySearch fails from quota/rate-limit/invalid-key/no-active-key,
do **not** abandon search. First run `keys status`; if no active key can serve the
request, run `register` or retry with `--auto_register`, then repeat the original
lightest suitable probe. Do not print full keys in the final answer.

## References

- Full vertical domain schemas: [references/domains.md](references/domains.md)
- Payload-control design spec: [references/design-v2.md](references/design-v2.md)

Call `get_sub_domains` live when precision matters — static references can lag
behind API changes.
