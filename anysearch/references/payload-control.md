# AnySearch Payload Control

AnySearch returns page-sized text blobs. The skill's job is to keep discovery
small, then deep-read only the pages that are worth the agent's context.

## Mental model

- **Search is discovery.** Use it to find candidate pages.
- **Extract is deep-read.** Use it after choosing a URL.
- **Format controls context, not network.** The AnySearch API still returns full
  text to the CLI; the CLI renders only the selected amount into stdout.

| Format | Role | Rendered output | Typical use |
|---|---|---|---|
| `compact` | discovery | rank, title, URL | Scan results and choose winners. |
| `snippet` | relevance check | compact + first `--max-chars` of body | Peek when titles are ambiguous. |
| `full` | deep-read | complete returned text | `extract`, or one-result quick answers. |

Defaults:

- `search` and `batch_search`: `compact`
- `extract`: `full`

## Discovery flow

```bash
# Discover candidates cheaply.
<cmd> search "WebGPU browser support" --format compact --max-results 8

# Deep-read only selected URLs.
<cmd> extract "https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API"
```

Use this flow unless the user explicitly wants one narrow top answer, where this
escape hatch is acceptable:

```bash
<cmd> search "current US inflation rate" --format full --max-results 1
```

## `compact`

Compact output contains one block per result:

```text
#1  Page title
    https://example.com/page
```

It is the safest discovery mode because every result is small and scannable.
Compact output ends with a short hint reminding the agent to use `snippet`,
`full`, or `extract` when more evidence is needed.

## `snippet`

Snippet output adds a clipped body preview:

```text
#1  Page title
    https://example.com/page
    First N characters of page body...
```

Snippets are **positional, not semantic**. The renderer skips a bounded amount
of obvious navigation/ad boilerplate, then takes the first `--max-chars` chars.
This works well for docs, papers, and reference pages where the lead carries the
answer. For news, blogs, and pages with heavy chrome, confirm important claims
with `extract`.

## `full`

Full output renders the returned page text as-is. It is appropriate when:

- a URL has already been selected and `extract` is being used;
- the user wants a narrow one-result answer and the top hit is likely enough;
- the search result itself must be preserved in full.

Do not use `full` as broad discovery.

## Dedup and rank

Search and batch search deduplicate by canonical URL unless `--no-dedup` is set.
The displayed URL stays unchanged; the dedup key normalizes scheme, strips
leading `www.`, removes fragments, trims root/trailing slashes, and sorts query
parameters.

The `#N` prefix is the relevance signal. AnySearch does not expose a numeric
score, so prefer lower ranks when deciding what to extract.

## Metadata header

Rendered output begins with a plain-text header:

```text
## "query" — 5 results (2 deduped), 1.4s, compact, 0.71 KB
```

For batch search:

```text
## batch(3 queries) — 12 results (1 deduped), 4.1s, snippet, 6.80 KB
```

For extract:

```text
## extract "https://example.com/page" — 1 result, 2.3s, full, 18.40 KB
```

The KB value is the exact UTF-8 size of the rendered body after trimming. It is
the number that matters for agent context budgeting.

## Maintainer checklist

When changing payload rendering or CLI help, verify:

- `search` and `batch_search` default to `compact`.
- `extract` defaults to `full`.
- Every example that discovers search results spells out `--format`.
- Compact output has only rank, title, and URL.
- Snippet output respects `--max-chars` and skips only obvious lead noise.
- Full output preserves complete returned text.
- Dedup removes cross-query duplicates unless `--no-dedup` is set.
- Metadata byte count matches the rendered body size.
- Format hints appear once for compact/snippet and never for full.
- CLI `--help`, `SKILL.md`, and this reference use the same vocabulary.
