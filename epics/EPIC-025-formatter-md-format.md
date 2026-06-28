# EPIC-025: Add Markdown Format to Formatter

## Goal

Add `md` as a third valid output format alongside `txt` and `html`. When `formatter.format: md` is set, the formatter converts each plain `.txt` output file to a `.md` file with minimal Markdown structure (preserving content, replacing the `.txt` file), exactly mirroring the `html` conversion pattern.

## Scope

- `config.py`: extend `load_config` validation to accept `"md"` in addition to `"txt"` and `"html"`.
- `pipeline/formatter.py`: add `"md"` branch to `format_file()` — read `.txt`, write `.md` with content wrapped in a fenced code block or as plain Markdown paragraphs (TBD during implementation), delete `.txt`.
- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: update the `format:` comment to show `txt | html | md`.
- Tests: add `test_formatter.py` cases — md run produces `.md`, no orphan `.txt`; txt and html runs unaffected; `--cleanup` removes `.md` outputs when format is `md`.

## Out of Scope

- Markdown templating / rich formatting (headings, metadata blocks) — plain paragraphs only for now.
- Changing any pipeline step other than `Formatter`.

## Acceptance Criteria

1. `formatter.format: md` in config is accepted without `ValueError`.
2. After a successful file pipeline step, `<file>.txt` is replaced by `<file>.md` (content identical, extension changed).
3. `formatter.format: txt` and `formatter.format: html` behaviour is unchanged.
4. `--cleanup` correctly removes `.md` files when format is `md`.
5. All existing tests pass; new formatter tests for `md` are green.
