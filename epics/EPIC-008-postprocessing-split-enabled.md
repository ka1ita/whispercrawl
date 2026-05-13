# EPIC-008: Split Postprocessing Enabled Flags

**Status**: Done

## Goal

Allow regex cleanup and LLM correction to be enabled/disabled independently in the `postprocessing` config section. Currently a single `enabled` flag controls both; disabling it skips the whole step including regex.

## Scope

- `src/fileswhisper/config.py` — add `regex_enabled: bool` to `OllamaStepConfig`; `enabled` is kept as the LLM flag (rename semantics only, no field rename for backwards compatibility)
- `src/fileswhisper/pipeline/postprocessor.py` — skip regex pass when `regex_enabled=False`; skip LLM call when `enabled=False`; return early if both disabled
- `src/fileswhisper/main.py` — instantiate `PostProcessor` when either `enabled` or `regex_enabled` is true
- `config/config.example.yaml` — document both flags
- `tests/test_pipeline/test_postprocessor.py` — add tests for each combination

## Config Interface

```yaml
postprocessing:
  enabled: true        # LLM correction via ollama (default: true)
  regex_enabled: true  # Regex cleanup pass (default: true)
```

| `enabled` | `regex_enabled` | Behaviour |
| --- | --- | --- |
| true | true | regex → LLM (current default) |
| false | true | regex only, no LLM call |
| true | false | LLM only, no regex pass |
| false | false | PostProcessor not instantiated |

## Acceptance Criteria

- [x] `regex_enabled: false` skips regex, still calls LLM
- [x] `enabled: false` (LLM disabled) still applies regex when `regex_enabled: true`
- [x] Both false → PostProcessor not instantiated, no ollama calls, no regex
- [x] Existing configs without `regex_enabled` behave identically to today (`regex_enabled` defaults to `true`)
- [x] Tests cover all four flag combinations

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
