---
name: anysearch
description: >-
  Probe the web for external information via AnySearch API. Use when the agent
  needs to look up, find, search, research, verify, check, investigate, or gather
  facts, news, prices, papers, code, people, companies, products, places, events,
  documentation, or any knowledge not already in context. Covers general web
  search, vertical domain search (finance, academic, code, health, legal,
  security, travel, energy, environment, agriculture, business, ip, gaming,
  film, social_media), parallel batch search (2–5 queries at once), and
  full-page URL content extraction as Markdown.
---

# anysearch

**Probe** the web via AnySearch — one API, four tools: `search`,
`get_sub_domains`, `batch_search`, `extract`.

## Route first

Every probe follows one of three paths. Pick by scanning the query:

| Signal | Path | First call |
|---|---|---|
| General knowledge, news, opinions, concepts — no structured identifier | **General** | `search` directly |
| Structured identifier (ticker, DOI, CVE, IATA) or specialized vertical (stock price, flight status, paper, drug info, weather, AQI) | **Vertical** | `get_sub_domains` → `search` |
| Ambiguous — could be both, or crosses multiple domains | **Hybrid** | `batch_search` with 1 general + N vertical |

**Done when** the path is chosen before any API call is made.

### Vertical gate

Before passing `--domain` to `search`, you MUST call `get_sub_domains` first.
The `sub_domain` and `sub_domain_params` come from its output — never guess.

**Done when** `sub_domain` is confirmed from `get_sub_domains` output.

## Commands

`<cmd>` = `python3 <skill-dir>/scripts/anysearch.py` (replace `<skill-dir>` with this skill's install path)

```bash
# General
<cmd> search "latest news on quantum computing" --max_results 5

# Vertical — get_sub_domains first, then search with sub_domain
<cmd> get_sub_domains --domains finance,code
<cmd> search "AAPL" --domain finance --sub_domain finance.quote --sdp type=stock,symbol=AAPL,cn_code=

# Hybrid — general + vertical in one batch
<cmd> batch_search --query "what is quantitative easing" --query "Fed funds rate 2025" --domain finance --sub_domain finance.macro --sdp type=fed_funds

# Extract — full page content as Markdown (50K char limit, HTML only)
<cmd> extract "https://example.com/article"

# Register a new account + create API key (no email needed)
<cmd> register                          # auto-gen username/password, add key to pool
<cmd> register -n 3                     # create 3 accounts+keys in one call
<cmd> register -k production-key          # custom key name
<cmd> register --print_only              # print only, don't add to pool
<cmd> register -u myuser -p mypass       # custom credentials

# Auto-register when all keys exhausted (per-call or via env var)
<cmd> --auto_register search "query"
# or persist via env: ANYSEARCH_AUTO_REGISTER=1
```

`--sdp` accepts `key=value` pairs (preferred) or JSON. Params marked `(required)`
in `get_sub_domains` output must all be passed; if a value is N/A, pass empty
string (`key=`). `batch_search` accepts up to 5 `--query` flags or a JSON array.

**Done when** API returns results without error.

## API key

Optional — anonymous access works with lower rate limits.

Key pool state is stored in `keys-state.json` (next to `SKILL.md`).
This is the single source of truth — no `.env` file needed.

**Manage keys:**
```bash
<cmd> keys list                       # show pool: status, call_count, last_used per key
<cmd> keys status                     # JSON summary
<cmd> keys add --key_value as_sk_xxx  # add an existing key manually
<cmd> keys remove --key_value as_sk_xxx  # remove a key
<cmd> keys prune                     # remove all dead keys
<cmd> keys config --rotation round-robin  # set rotation mode
<cmd> keys config --auto_register true     # enable auto-register
```

**Create keys:**
```bash
<cmd> register                       # register account + create key, add to pool
<cmd> register -n 3                  # create 3 at once
<cmd> register -k production-key     # custom key name
<cmd> register --print_only           # print only, don't add to pool
```

**Auto-register** — when all keys are exhausted, automatically register a new
account + create a key instead of falling back to anonymous:
```bash
<cmd> --auto_register search "query"
<cmd> keys config --auto_register true   # persist in keys-state.json
```

When a key returns `invalid_api_key` or quota exhausted, the script marks it
dead in `keys-state.json` and rotates to the next key. If all keys are dead,
it falls back to anonymous (or auto-registers a fresh key if enabled).
If the API auto-registers a new key, it's added to the pool automatically.

## Domains

`general` `finance` `academic` `code` `health` `legal` `security` `business` `ip`
`energy` `environment` `agriculture` `travel` `film` `gaming` `social_media` `resource`

For full sub_domain schemas and parameter details, see
[references/domains.md](references/domains.md). Call `get_sub_domains` live for
the latest schema — the reference may lag behind API updates.

## Key rotation flow

```
keys-state.json (single source of truth)
  → load active keys → build pool
  → try key[0] → isError? → mark dead in state → try key[1] → … → key[N]
  → all dead?
    → auto_register enabled? → register new account + create key → add to pool → retry
    → else → anonymous fallback
  → API returns auto_registered key? → add to pool
```

## Self-serve register flow

```
register subcommand
  → POST /api/ssuser/auth/register (username, password, agreement=true)
  → POST /api/api/user/keys (Bearer access_token)
  → add key to keys-state.json pool
  → output JSON: [{username, password, api_key, key_id, key_name}]
```

Rate limits: the register endpoint has an upstream rate limit (~1 req/min).
If you get `42901`, wait 60-120s and retry.