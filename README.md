# anysearch skill

Agent-friendly AnySearch skill: general web search, vertical search, batch search,
URL extraction, multi-key rotation, and self-serve key creation.

## Install

```bash
npx skills add catoncat/anysearch-skill --yes --global
```

The skill payload lives in [`anysearch/`](anysearch/). Keeping the skill in a
subdirectory ensures installers copy bundled `scripts/` and `references/` along
with `SKILL.md`.

## Features

- **Probe → Extract workflow** — search/batch are compact discovery steps;
  extract deep-reads selected URLs.
- **Payload controls** — `--format compact|snippet|full`, `--max-chars`, exact
  output-size headers, and default URL deduplication.
- **Vertical domains** — finance, academic, code, health, legal, security,
  travel, business, social media, and more.
- **Multi-key rotation** — fallback and round-robin modes with per-key state.
- **Self-serve key creation** — `register` creates accounts + API keys when
  needed; `--auto_register` can provision a fresh key when the pool is dead.
- **Stdlib-only CLI** — no pip dependencies.

## CLI quick start

After install:

```bash
CMD="python3 ~/.agents/skills/anysearch/scripts/anysearch.py"

$CMD search "Cloudflare Workers 2026" --format compact --max-results 8
$CMD search "Python asyncio gather exception handling" --format snippet --max-results 3
$CMD search "current US inflation rate 2025" --format full --max-results 1
$CMD extract "https://example.com/article"
$CMD batch_search --query "PostgreSQL performance" --query "MySQL performance" --format compact
```

## Key pool state

Runtime key state is local, ignored by Git, and stored outside the install
directory so `npx skills add/update` can safely overwrite the skill:

```text
macOS:   ~/Library/Application Support/anysearch/keys-state.json
Linux:   ${XDG_CONFIG_HOME:-~/.config}/anysearch/keys-state.json
Windows: %APPDATA%\\AnySearch\\keys-state.json
```

Legacy install-local `keys-state.json` / `.env` files are migrated on first run.
Use `ANYSEARCH_CONFIG_DIR=/custom/path` to override the location.

Use the CLI to manage it:

```bash
$CMD keys list
$CMD keys add --key_value as_sk_xxx
$CMD keys config --rotation round-robin
$CMD keys config --auto_register true
$CMD register -n 3
```

Never commit real API keys. See
[`anysearch/keys-state.example.json`](anysearch/keys-state.example.json) for the
schema.

## References

- Skill instructions: [`anysearch/SKILL.md`](anysearch/SKILL.md)
- Payload design: [`anysearch/references/design-v2.md`](anysearch/references/design-v2.md)
- Domain schemas: [`anysearch/references/domains.md`](anysearch/references/domains.md)

## License

MIT
