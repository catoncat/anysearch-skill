# anysearch skill

Agent-friendly AnySearch: a Pi/Codex-style skill plus a bundled stdlib-only CLI
that keeps web discovery cheap, then deep-reads only the sources worth putting
in context.

## Install

```bash
npx skills add catoncat/anysearch-skill --yes --global
```

Update an existing install from the published repository:

```bash
npx skills update catoncat/anysearch-skill --yes --global
```

After install or update, the skill payload is copied to:

```text
~/.agents/skills/anysearch/
```

The important files are:

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

## Quick use

```bash
CMD="python3 ~/.agents/skills/anysearch/scripts/anysearch.py"
```

Light discovery:

```bash
$CMD search "Cloudflare Workers 2026" --format compact --max-results 5
```

Deep-read a selected URL:

```bash
$CMD extract "https://developers.cloudflare.com/workers/"
```

Compare several angles without flooding context:

```bash
$CMD batch_search \
  --query "Cloudflare Workers deployment" \
  --query "Cloudflare Workers observability" \
  --query "Cloudflare Workers pricing" \
  --format compact --max-results 5
```

Use a vertical schema safely:

```bash
$CMD get_sub_domains --domains finance,code
$CMD search "AAPL" --domain finance --sub_domain finance.quote \
  --sdp type=stock,symbol=AAPL,cn_code= --format compact --max-results 3
```

Inspect or create keys when anonymous access is not enough:

```bash
$CMD keys status
$CMD register
$CMD keys config --rotation round-robin
$CMD --auto_register search "current US inflation rate" --format compact
```

## How this differs from official AnySearch

This repository does not replace the official AnySearch service or API. It wraps
AnySearch for coding agents that need predictable, low-context web research.

The wrapper adds:

- **Probe → extract workflow** — search/batch are discovery steps; `extract`
  deep-reads selected URLs.
- **Compact discovery by default** — search results render as rank, title, and
  URL unless the agent asks for snippets or full text.
- **Context-aware payload controls** — `--format compact|snippet|full`,
  `--max-chars`, default URL deduplication, and exact rendered-size headers.
- **Bundled CLI** — `scripts/anysearch.py` uses Python's standard library only;
  no pip install is required.
- **Key pool recovery** — saved keys, fallback or round-robin rotation,
  `register`, and optional `--auto_register` when quota/auth fails.
- **Live vertical schema discipline** — agents are told to call
  `get_sub_domains` before structured vertical search instead of guessing
  `sub_domain` or `--sdp` parameters.

## Key state

Runtime key state is local to your user account and is not stored in the skill
install directory:

```text
macOS:   ~/Library/Application Support/anysearch/keys-state.json
Linux:   ${XDG_CONFIG_HOME:-~/.config}/anysearch/keys-state.json
Windows: %APPDATA%\AnySearch\keys-state.json
```

Override for tests or unusual deployments:

```bash
ANYSEARCH_CONFIG_DIR=/custom/path $CMD keys status
```

Never commit real API keys. The checked-in
[`anysearch/keys-state.example.json`](anysearch/keys-state.example.json) is only
a schema example.

## Repository layout

The installable skill lives in [`anysearch/`](anysearch/):

- [`anysearch/SKILL.md`](anysearch/SKILL.md) — agent-facing process.
- [`anysearch/scripts/anysearch.py`](anysearch/scripts/anysearch.py) — bundled CLI.
- [`anysearch/references/payload-control.md`](anysearch/references/payload-control.md) — payload modes and renderer rules.
- [`anysearch/references/keys.md`](anysearch/references/keys.md) — key pool details.
- [`anysearch/references/domains.md`](anysearch/references/domains.md) — static vertical schema snapshot; call `get_sub_domains` live for precision.

## License

MIT
