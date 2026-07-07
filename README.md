# AnySearch Skill

<p align="center">
  <img src="assets/anysearch-banner.png" alt="AnySearch skill mascot — probe the web, extract what matters" width="100%" />
</p>

Agent-friendly **AnySearch** for coding agents: a Pi/Codex-style skill plus a bundled stdlib-only CLI that keeps web discovery cheap, then deep-reads only the sources worth putting in context.

**Probe first. Extract only what earns the context.**

## Install

```bash
npx skills add catoncat/anysearch-skill --yes --global
```

Update an existing install:

```bash
npx skills update catoncat/anysearch-skill --yes --global
```

After install or update, the skill payload is copied to:

```text
~/.agents/skills/anysearch/
```

Important files:

```text
~/.agents/skills/anysearch/SKILL.md
~/.agents/skills/anysearch/scripts/anysearch.py
~/.agents/skills/anysearch/references/
```

Quick verification:

```bash
CMD="python3 ~/.agents/skills/anysearch/scripts/anysearch.py"
$CMD --help
$CMD search "Cloudflare Workers 2026" --format compact --max-results 5
```

## Optional: faster local extraction

The CLI runs with zero `pip` dependencies. For faster, private `extract` with
no external round-trip, install the readability executable — the skill detects
it on `PATH` automatically:

```bash
# needs Node; outputs clean Markdown (recommended)
npm i -g defuddle
# (or just run `npx defuddle` once to fill the npm cache, no global install)
```

No config change needed. Without it, `extract` falls back to hosted readers
(`r.jina.ai`, then `defuddle.md` in series), then the AnySearch API. Each remote
reader fires only if the prior one fails, so a normal extract costs at most one
reader's quota.

## Quick use

```bash
CMD="python3 ~/.agents/skills/anysearch/scripts/anysearch.py"
```

**Light discovery**

```bash
$CMD search "Cloudflare Workers 2026" --format compact --max-results 5
```

**Deep-read a selected URL**

```bash
$CMD extract "https://developers.cloudflare.com/workers/"
```

**Compare several angles**

```bash
$CMD batch_search \
  --query "Cloudflare Workers deployment" \
  --query "Cloudflare Workers observability" \
  --query "Cloudflare Workers pricing" \
  --format compact --max-results 5
```

**Vertical search (schema first)**

```bash
$CMD get_sub_domains --domains finance,code
$CMD search "AAPL" --domain finance --sub_domain finance.quote \
  --sdp type=stock,symbol=AAPL,cn_code= --format compact --max-results 3
```

**Keys when anonymous access is not enough**

```bash
$CMD keys status
$CMD register
$CMD keys config --rotation round-robin
$CMD --auto_register search "current US inflation rate" --format compact
```

## How this differs from official AnySearch

This repository does not replace the official AnySearch service or API. It wraps AnySearch for agents that need predictable, low-context web research.

| What you get | Why it matters |
|--------------|----------------|
| **Probe → extract** | Search/batch discover; `extract` deep-reads winners only. |
| **Compact by default** | Rank, title, URL unless you ask for snippets or full text. |
| **Payload controls** | `--format compact\|snippet\|full`, `--max-chars`, dedup, size headers. |
| **Bundled CLI** | `anysearch.py` — stdlib only, no pip install. |
| **Key pool recovery** | Saved keys, rotation, `register`, `--auto_register`. |
| **Live vertical schema** | `get_sub_domains` before guessing `sub_domain` / `--sdp`. |

## Key state

Runtime key state is local to your account (not in the skill install dir):

```text
macOS:   ~/Library/Application Support/anysearch/keys-state.json
Linux:   ${XDG_CONFIG_HOME:-~/.config}/anysearch/keys-state.json
Windows: %APPDATA%\AnySearch\keys-state.json
```

Override:

```bash
ANYSEARCH_CONFIG_DIR=/custom/path $CMD keys status
```

Never commit real API keys. [`anysearch/keys-state.example.json`](anysearch/keys-state.example.json) is schema-only.

## Repository layout

| Path | Role |
|------|------|
| [`anysearch/SKILL.md`](anysearch/SKILL.md) | Agent-facing process |
| [`anysearch/scripts/anysearch.py`](anysearch/scripts/anysearch.py) | Bundled CLI |
| [`anysearch/references/`](anysearch/references/) | Payload, keys, domains docs |
| [`assets/anysearch-banner.png`](assets/anysearch-banner.png) | README banner art |

## License

MIT