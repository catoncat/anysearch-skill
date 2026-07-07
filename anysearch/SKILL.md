---
name: anysearch
description: >-
  Probe the web with AnySearch when current facts, source discovery, URL
  extraction, multi-angle comparison, or live vertical schemas are needed.
  Use a compact probe first, extract selected URLs only when evidence is
  needed, and recover through the key pool on auth/quota failures.
---

# anysearch

**Probe first. Extract only what earns the context.**

`<cmd>` = `python3 <skill-dir>/scripts/anysearch.py`

## Core loop

1. Choose the smallest rung in the effort ladder that can satisfy the user.
2. Run the probe in compact form unless the rung says otherwise.
3. Stop when the completion column is met; otherwise extract selected URLs or
   move one rung up.
4. Answer from extracted/source evidence, not from raw result lists, when the
   user needs supportable claims.
5. If access fails from auth, quota, rate limit, or no active key, run the key
   recovery branch and then repeat the original smallest suitable probe.

Hard constraints:

- `full` is not a discovery default. Use it only for `extract` or a one-result
  quick answer.
- `extract` follows selection. Do not deep-read every search result by habit.
- Vertical search starts with live schema: never invent `sub_domain` or `--sdp`.

## Effort ladder

| User need | Rung | Do | Completion criterion |
|---|---|---|---|
| Quick lookup, sanity check, or “what exists?” | **Light probe** | `search --format compact --max-results 5` | The visible titles/URLs directly answer the user or expose enough candidates to choose the next move. |
| Answer needs citations, comparison of sources, or source quality | **Standard probe** | `search --format compact --max-results 8` → `extract` 1–3 winners | Each factual claim in the answer is grounded in an extracted or clearly named source. |
| Titles do not reveal relevance | **Sample probe** | `search --format snippet --max-results 3 --max-chars 500` | You can choose winners, reformulate the query, or stop because the candidates are visibly irrelevant. |
| Landscape, tradeoffs, trends, competitors, strategy, or “what do people think?” | **Deep probe** | `batch_search` with 3–5 distinct queries, compact, `--max-results 5` → extract 3–5 distinct winners | The answer covers each angle; duplicate URLs are not re-read. |
| Ticker, DOI, CVE, package, code, flight, legal, medical, finance, or other structured identifier | **Vertical probe** | `get_sub_domains` → `search --domain ... --sub_domain ... --sdp ...` | Required params came from live schema and the query uses the matching vertical. |
| User asks for one top answer and narrow evidence is acceptable | **Quick full** | `search --format full --max-results 1` | The top result is authoritative enough; if it looks wrong or thin, fall back to Standard. |

## Commands

```bash
# Light probe
<cmd> search "Cloudflare Workers 2026" --format compact --max-results 5

# Standard probe: discover, then deep-read selected winners
<cmd> search "WebGPU browser support 2025" --format compact --max-results 8
<cmd> extract "https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API"

# Sample probe: peek before committing to extraction
<cmd> search "Rust async runtime comparison" --format snippet --max-results 3 --max-chars 500

# Deep probe: compare several angles without rereading duplicate URLs
<cmd> batch_search \
  --query "Cloudflare Workers deployment" \
  --query "Cloudflare Workers observability" \
  --query "Cloudflare Workers pricing" \
  --format compact --max-results 5

# Quick full: one result, full content
<cmd> search "current US inflation rate" --format full --max-results 1

# Vertical probe: schema first, then structured search
<cmd> get_sub_domains --domains finance,code
<cmd> search "AAPL" --domain finance --sub_domain finance.quote \
  --sdp type=stock,symbol=AAPL,cn_code= --format compact --max-results 3
```

Options used most often:

- `--format compact|snippet|full` — search/batch default `compact`; extract default `full`.
- `--max-results N` / `--max_results N` / `-m N` — cap results, max 10.
- `--max-chars N` — snippet character budget, default 500.
- `--no-dedup` — keep duplicate URLs only when duplicates are meaningful.
- `--domain`, `--sub_domain`, `--sdp` — vertical controls; call `get_sub_domains` first.
- `--reader auto|local|remote|anysearch` — `extract` body backend. `auto`
  (default) prefers local readability when installed, else tries remote
  readers in series, else the AnySearch API; `anysearch` forces the API. See
  [references/payload-control.md](references/payload-control.md).

`--sdp` accepts `key=value` pairs or JSON. Params marked required must all be
passed; if a required value is unavailable, pass an empty string (`key=`) rather
than omitting the key.

## Key recovery branch

Normal searches use anonymous access or the saved key pool automatically.
`auto_register` is **on by default**: if no active key can serve a probe, the
CLI creates a throwaway account and key for you and stores them locally — so
most access failures self-heal without agent action. Step in only when that
itself fails or the user wants to manage keys:

1. Run `<cmd> keys status` to see the pool.
2. If auto-register failed or the user wants explicit control, run
   `<cmd> register`, or `keys config --auto_register false` to turn the
   default off, then retry.
3. Repeat the original smallest suitable probe.
4. Never print full API keys in the final answer.

For key paths, rotation, manual seeding, and persistent auto-register, read
[references/keys.md](references/keys.md).

## References

- Payload controls: [references/payload-control.md](references/payload-control.md)
- Key pool details: [references/keys.md](references/keys.md)
- Static vertical catalog: [references/domains.md](references/domains.md)

Call `get_sub_domains` live when vertical precision matters; the static catalog
is only a convenience snapshot.
