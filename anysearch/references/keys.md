# AnySearch Key Pool

The CLI can use anonymous access, a saved pool of API keys, or a one-shot key.
The agent should treat key handling as a recovery branch: search first, inspect
keys only when access fails or the user asks to manage them.

## Runtime state

Key state is local to the user and intentionally outside the skill install
directory, so reinstalling or updating the skill does not erase keys.

```text
macOS:   ~/Library/Application Support/anysearch/keys-state.json
Linux:   ${XDG_CONFIG_HOME:-~/.config}/anysearch/keys-state.json
Windows: %APPDATA%\AnySearch\keys-state.json
```

Override for tests or custom deployments:

```bash
ANYSEARCH_CONFIG_DIR=/custom/path <cmd> keys status
```

On first run, the CLI also imports any existing install-local `keys-state.json`,
`.env`, `ANYSEARCH_API_KEY`, or `ANYSEARCH_API_KEYS` values into this state file.

## Inspect without leaking secrets

```bash
<cmd> keys status
<cmd> keys list
```

`keys list` prints key prefixes, status, source, call counts, and last-used time;
it does not print full key values.

## Seed or expand the pool

```bash
# Create one account + API key and save it to the pool.
<cmd> register

# Create several keys.
<cmd> register -n 5

# Add a key you already have.
<cmd> keys add --key_value as_sk_xxx --key_name personal
```

`register` prints newly created credentials to stdout. Do not copy full keys or
passwords into final user-facing answers unless the user explicitly asks for
that sensitive output.

## Rotation modes

```bash
# Default: use key 1 until it dies, then key 2, then anonymous.
<cmd> keys config --rotation fallback

# Spread calls across active keys.
<cmd> keys config --rotation round-robin
```

Dead keys are skipped. Remove them when desired:

```bash
<cmd> keys prune
```

## Auto-register

Persistent unattended recovery:

```bash
<cmd> keys config --auto_register true
```

One-shot recovery for a single call:

```bash
<cmd> --auto_register search "query" --format compact
```

`--auto_register` is a global option, so it appears before the subcommand.

## Recovery loop for agents

When a search fails from quota, rate limit, invalid key, or no active key:

1. Run `<cmd> keys status`.
2. If there is an active key, retry the original command once.
3. If there is no active key, run `<cmd> register` or retry the original command
   with global `--auto_register`.
4. Repeat the original smallest suitable probe.
5. Report the search result, not the key material.
