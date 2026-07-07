# anysearch

A [pi](https://github.com/earendil-works/pi) skill that probes the web via
[AnySearch](https://anysearch.com) — one API, four tools: `search`,
`get_sub_domains`, `batch_search`, `extract`.

## Features

- **Multi-key rotation** with per-key state tracking (call count, last used,
  status: active/exhausted/invalid)
- **Self-serve key creation** — `register` subcommand creates new accounts +
  API keys on demand, no email required
- **Auto-register** — automatically provisions a fresh key when all keys are
  exhausted
- **Key pool management** — `keys` subcommand to list, add, remove, prune,
  and configure the pool
- **Stdlib-only** Python script — no pip dependencies

## Install

```bash
git clone https://github.com/catoncat/anysearch-skill.git ~/.pi/agent/skills/anysearch
```

## Usage

```bash
CMD="python3 ~/.pi/agent/skills/anysearch/scripts/anysearch.py"

# Search
$CMD search "latest news on quantum computing" --max_results 5

# Vertical search
$CMD get_sub_domains --domains finance,code
$CMD search "AAPL" --domain finance --sub_domain finance.quote --sdp type=stock,symbol=AAPL,cn_code=

# Batch search (up to 5 queries)
$CMD batch_search --query "what is quantitative easing" --query "Fed funds rate 2025"

# Extract page content as Markdown
$CMD extract "https://example.com/article"

# Register a new account + create API key
$CMD register                    # auto-gen credentials, add to pool
$CMD register -n 3               # create 3 keys
$CMD register -k production-key   # custom key name

# Manage key pool
$CMD keys list                    # show all keys with status + usage
$CMD keys status                  # JSON summary
$CMD keys add --key_value as_sk_xxx
$CMD keys remove --key_value as_sk_xxx
$CMD keys prune                   # remove dead keys
$CMD keys config --rotation round-robin
$CMD keys config --auto_register true
```

## Key pool state

All key state lives in `keys-state.json` (gitignored). See
`keys-state.example.json` for the schema.

## License

MIT
