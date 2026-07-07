---
name: anysearch
description: >-
  Probe the web for external information via AnySearch API. Use when the agent
  needs to look up, find, search, research, verify, check, investigate, or gather
  facts, news, prices, papers, code, people, companies, products, places, events,
  documentation, or any knowledge not already in context. Covers general web
  search, vertical domain search (finance, academic, code, health, legal,
  security, travel, energy, environment, agriculture, business, ip, gaming,
  film, social_media), parallel batch search, and URL extraction. Agent-friendly
  payload controls default to compact search results to avoid context blowups.
---

# anysearch

**Probe → Extract** with AnySearch.

- `search` / `batch_search` are for **discovery**: find candidate URLs.
- `extract` is for **deep-read**: read one chosen URL.
- Default search output is compact to protect context; explicitly ask for more.

`<cmd>` = `python3 <skill-dir>/scripts/anysearch.py`.

## Format decision

| Agent is... | Use | Results | Then |
|---|---|---:|---|
| **Exploring**: “what exists on X?” | `search --format compact` | 5–10 | scan titles → `extract <URL>` winners |
| **Evaluating**: “is this relevant?” | `search --format snippet` | 3–5 | if confirmed → `extract <URL>` |
| **Deep-reading**: “give me full search results” | `search --format full` | 1–3 | done |
| **Comparing**: “N aspects of X” | `batch_search --format compact` | 5/query | extract distinct winners |
| **Quick answer**: “top hit is enough” | `search --format full --max-results 1` | 1 | done |

Notes:

1. `compact` = rank + title + URL. `snippet` = compact + first N chars. `full` = complete API content.
2. `snippet` is positional, not semantic. It skips obvious nav/ad lead noise, then takes the first `--max-chars` chars. For blogs/news with heavy chrome, confirm with `extract`.
3. `--format` trims client-side. AnySearch still sends full data to the script; this saves **agent context**, not network latency.
4. Search and batch dedup by canonical URL by default. Use `--no-dedup` only when duplicates matter.
5. `#N` rank is the relevance signal; AnySearch does not expose a numeric score.
6. `extract` defaults to `--format full` because the URL has already been selected.

## Commands

```bash
# General discovery (safe default: compact)
<cmd> search "Cloudflare Workers 2026" --format compact --max-results 8

# Evaluate candidates with short previews
<cmd> search "Python asyncio gather exception handling" --format snippet --max-results 3 --max-chars 500

# Quick one-shot answer
<cmd> search "current US inflation rate 2025" --format full --max-results 1

# Deep-read a chosen URL
<cmd> extract "https://example.com/article"                 # full by default
<cmd> extract "https://example.com/article" --format snippet --max-chars 800

# Batch comparison (max 5 queries, dedup on by default)
<cmd> batch_search --query "PostgreSQL performance" --query "MySQL performance" --format compact --max-results 5
```

Options:

- `--format compact|snippet|full` — search/batch default `compact`; extract default `full`.
- `--max-results N` / `--max_results N` / `-m N` — cap results, max 10.
- `--max-chars N` — snippet char budget, default 500.
- `--no-dedup` — disable URL dedup for search/batch.

## Route first

| Signal | Path | First call |
|---|---|---|
| General knowledge, news, opinions, concepts — no structured identifier | **General** | `search --format compact` |
| Structured identifier (ticker, DOI, CVE, IATA) or specialized vertical | **Vertical** | `get_sub_domains` → `search` |
| Ambiguous or crosses multiple aspects | **Hybrid** | `batch_search --format compact` |

Before passing `--domain` to `search`, call `get_sub_domains` first. The
`sub_domain` and required `sub_domain_params` come from live output — never guess.

```bash
# Discover vertical schema first
<cmd> get_sub_domains --domains finance,code

# Then call vertical search with confirmed params
<cmd> search "AAPL" --domain finance --sub_domain finance.quote \
  --sdp type=stock,symbol=AAPL,cn_code= --format compact --max-results 3
```

`--sdp` accepts `key=value` pairs or JSON. Params marked required must all be
passed; if a value is N/A, pass empty string (`key=`).

## End-to-end patterns

### Explore then extract

```bash
<cmd> search "WebGPU browser support 2025" --format compact --max-results 8
# choose authoritative URLs from #1..#8
<cmd> extract "https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API"
```

### Evaluate before committing context

```bash
<cmd> search "Rust async runtime comparison" --format snippet --max-results 4 --max-chars 400
# if one result is promising, deep-read it
<cmd> extract "https://tokio.rs/tokio/tutorial"
```

### Compare several angles

```bash
<cmd> batch_search \
  --query "Cloudflare Workers deployment" \
  --query "Cloudflare Workers observability" \
  --query "Cloudflare Workers pricing" \
  --format compact --max-results 5
# deduped candidate list → extract 2–4 winners
```

## Key pool

Anonymous access works with lower limits. Key pool state lives in
`keys-state.json` next to `SKILL.md`.

```bash
<cmd> keys list                         # status, call_count, last_used per key
<cmd> keys status                       # JSON summary
<cmd> keys add --key_value as_sk_xxx    # add existing key
<cmd> keys remove --key_value as_sk_xxx # remove key
<cmd> keys prune                        # remove dead keys
<cmd> keys config --rotation round-robin
<cmd> keys config --auto_register true
```

Rotation modes:

- `fallback`: key1 until exhausted → key2 → … → anonymous.
- `round-robin`: cycle keys on each call; dead keys are skipped.

When a key returns `invalid_api_key`, quota, or rate-limit errors, the script
marks it dead and rotates. If all keys are dead, it falls back to anonymous or
auto-registers if enabled.

```bash
<cmd> register                 # register account + create key + add to pool
<cmd> register -n 3            # create 3 accounts+keys
<cmd> register --print_only    # print credentials/key without adding
<cmd> --auto_register search "query" --format compact
```

## References

- Full vertical domain schemas: [references/domains.md](references/domains.md)
- Payload-control design spec: [references/design-v2.md](references/design-v2.md)

Call `get_sub_domains` live when precision matters — static references can lag
behind API changes.
