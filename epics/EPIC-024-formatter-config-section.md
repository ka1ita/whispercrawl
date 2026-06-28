# EPIC-024: Formatter Config Section

**Status**: Open

## Goal

Replace the top-level `output_format` key with a dedicated `formatter:` section in the config file, consistent with all other pipeline step sections (`transcription:`, `postprocessing:`, etc.). Add an `enabled` flag so the format conversion step can be turned off without removing the format setting.

## Background

EPIC-022 added `output_format` as a top-level key. EPIC-023 introduced the `Formatter` class as a proper pipeline step. Now that Formatter is a first-class step, it deserves its own config section — just like every other pipeline step has `transcription:`, `postprocessing:`, etc.

This also enables `enabled: false` to skip the conversion step (useful for debugging or when downstream tooling prefers plain `.txt` but the default format is `html`).

---

## Scope

### New dataclass — `FormatterConfig`

Add to `config.py`:

```python
@dataclass
class FormatterConfig:
    format: str = "txt"    # "txt" | "html"
    enabled: bool = True   # false = skip conversion; files stay as .txt
```

### `Config` changes

- Replace `output_format: str = "txt"` with `formatter: FormatterConfig = field(default_factory=FormatterConfig)`
- Remove the `output_format` field entirely

### `load_config()` changes

- Read `formatter:` section from YAML via `_build(FormatterConfig, raw.get("formatter", {}))`
- Move the format validation (`"txt"` or `"html"`) into `load_config` after building `FormatterConfig`
- Remove the `output_format` top-level read (`raw.get("output_format", "txt")`)

### `main.py` changes

- Replace `config.output_format` → `config.formatter.format` at all call sites:
  - `Formatter(fmt)` construction in `run_pipeline()`
  - `Cleaner(config.cleanup, fmt)` construction
  - `run_cleanup()` — `fmt = config.formatter.format`
  - `iter_media_files(…, config.formatter.format)` call
- Gate `Formatter` construction on `config.formatter.enabled`: when `enabled=False`, use `Formatter("txt")` (no-op) regardless of `format`

### `file_walker.py` — no change needed

`iter_media_files` receives `output_format` as a plain `str` from the caller in `main.py`; the caller is the only thing that changes.

### Config files

Update `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`:

```yaml
# ── Formatter ─────────────────────────────────────────────────────────────────
formatter:
  format: html        # txt | html (default: txt)
  # enabled: true     # set to false to skip format conversion
```

Remove the now-replaced `output_format:` top-level line.

---

## Acceptance Criteria

- [ ] `FormatterConfig` dataclass exists in `config.py` with `format` and `enabled` fields
- [ ] `Config.output_format` is gone; `Config.formatter: FormatterConfig` takes its place
- [ ] `load_config()` reads `formatter:` section; raises `ValueError` on unknown `format` value
- [ ] All `config.output_format` references in `main.py` replaced with `config.formatter.format`
- [ ] `enabled: false` causes the Formatter to be a no-op (files stay as `.txt`) even when `format: html`
- [ ] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml` use the new `formatter:` section; top-level `output_format:` removed
- [ ] All existing tests updated to use `Config(formatter=FormatterConfig(...))` instead of `Config(output_format=...)`
- [ ] New test: `enabled: false` with `format: html` → output files remain `.txt`

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
