# EPIC-022: Configurable Output Format (TXT / HTML)

**Status**: Open

## Goal

Add a single global `output_format` setting (`"txt"` or `"html"`) that controls the file extension and content encoding for all pipeline output files.

Decouple the step suffix labels (e.g. `_fix`, `_sum`) from the file extension so that the extension is derived from `output_format` rather than hard-coded into each `output_suffix` field.

## Background

All pipeline steps currently embed `.txt` into `output_suffix` values (`.txt`, `_fix.txt`, `_sum.txt`, `_err.txt`).  
Adding an HTML mode requires either duplicating that extension in every step or centralising the extension in one place.  
The cleaner design is: **suffix = label only** (`""`, `"_fix"`, `"_sum"`, `"_err"`); **extension = format** (`.txt` or `.html`).

---

## Scope

### Config changes

- Add `output_format: "txt"` to `Config` (global; default `"txt"`; accepted values `"txt"` | `"html"`).
- Change all default `output_suffix` and `error_suffix` values to **label only** (no extension):
  - `TranscriptionConfig.output_suffix`: `""` (was `".txt"`)
  - `TranscriptionConfig.error_suffix`: `"_err"` (was `"_err.txt"`)
  - `OllamaStepConfig.output_suffix`: step-specific defaults `"_fix"`, `"_sum"` (were `"_fix.txt"`, `"_sum.txt"`)
  - `OllamaStepConfig.error_suffix`: `"_err"` (was `"_err.txt"`)
  - `CleanupConfig.targets`: `["", "_fix", "_sum", "_diarize.json"]` (json stays unchanged; `.txt`-based entries removed)
- `load_config` validates `output_format` value; raises `ValueError` on unknown format.

### Filename construction

Introduce a helper `output_path(file_path, suffix, fmt) -> Path` (in `main.py` or a small util):

```python
def output_path(base: Path, suffix: str, fmt: str) -> Path:
    ext = ".html" if fmt == "html" else ".txt"
    return base.with_name(base.stem + suffix + ext)
```

Replace all ad-hoc `file_path.with_name(stem + suffix)` calls in `main.py` and `summarizer.py` with this helper.

Also update `iter_media_files` in `file_walker.py`: pass `output_format` alongside `transcription_suffix` so the skip-check uses the correct extension.

### HTML rendering

Add `render_output(text: str, fmt: str) -> str` helper (in `main.py` or a util):

- `"txt"`: return `text` unchanged.
- `"html"`: wrap in a minimal HTML shell:

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body><pre>CONTENT</pre></body>
</html>
```

Where `CONTENT` is `text` with `&`, `<`, `>` HTML-escaped. Apply this before every `write_text` call in `run_pipeline`.

### config.yaml

Add `output_format: txt` entry (top-level, before `transcription:`).  
Update all `output_suffix` / `error_suffix` examples to label-only form.  
Update `cleanup.targets` list accordingly.

### deploy configs

Update `deploy/prod/config.yaml` and `deploy/prod-local/config.yaml` the same way.

---

## Acceptance Criteria

- [ ] `Config.output_format` exists; defaults to `"txt"`; `load_config` raises on unknown value
- [ ] All `output_suffix` / `error_suffix` defaults no longer contain `.txt`
- [ ] `output_path()` helper used for every output file written in `main.py` and every glob pattern in `summarizer.py`
- [ ] `iter_media_files` skip-check uses `output_format` to derive the correct extension
- [ ] `cleanup.targets` defaults updated; `--cleanup` still removes all pipeline outputs
- [ ] `render_output("txt")` returns text unchanged; `render_output("html")` wraps in escaped HTML
- [ ] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml` updated
- [ ] Existing tests updated / new tests added: TXT path unchanged; HTML path produces valid shell; cleanup removes `.html` files when format is html
- [ ] `diarize_log` JSON sidecar (`_diarize.json`) is unaffected — always written as `.json`

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
