# EPIC-062: Fix Directory-Result Filename Corruption for Directories Whose Name Contains `_`

## Goal

Reported symptom (production, RedOS 8): when a watched directory's name
contains an underscore — e.g. `dir_xxx` — the per-directory result file the
pipeline writes comes out mangled, e.g. `_xxx.html` instead of the expected
`_dir_xxx.html` (or `_dir_xxx_<engine>.html` with a named engine): the first
segment of the directory name (`dir`) and the engine label are both missing.

This epic tracks reproducing that failure against the current codebase,
finding its root cause, and fixing it so that **any** directory name —
regardless of how many underscores it contains, where they fall, or whether
they happen to collide with the configured engine name or
`dir_summarization.underscore_prefix` — always round-trips into a directory
result filename that contains the full, unmodified directory name plus the
configured prefix and engine label.

## Problem Description

- The per-directory pass builds the result filename in `run_pipeline()`:
  - `prefix = "_" if config.dir_summarization.underscore_prefix else ""`
    ([main.py:697](../src/asr_crawler/main.py#L697))
  - `elabel = engine_label(eng_name)` ([main.py:738](../src/asr_crawler/main.py#L738)),
    where `engine_label` returns `f"_{name}"` or `""`
    ([config.py:56-58](../src/asr_crawler/config.py#L56))
  - `dir_base = dir_path / (prefix + dir_path.name + elabel)`
    ([main.py:739](../src/asr_crawler/main.py#L739))
  - `dir_result_path = output_path(dir_base, "", "txt")`
    ([main.py:775](../src/asr_crawler/main.py#L775)), where `output_path` does
    `base.with_name(base.stem + suffix + ext)` ([main.py:30-37](../src/asr_crawler/main.py#L30))
  - the `.txt` is later converted in place via `Formatter.format_file()`, which
    uses `txt_path.with_suffix(".html"/".md")`
    ([pipeline/formatter.py:89-109](../src/asr_crawler/pipeline/formatter.py#L89))
- **Investigation so far**: driving `run_pipeline()` end-to-end (transcriber
  mocked) against directory names `dir_xxx`, `_xxx`, `dir_`, `a_b_c`,
  `__dir__xxx`, `dir_xxx_`, crossed with `underscore_prefix` true/false and
  zero/one/two named engines, consistently produced the *correct* filename
  (e.g. `dir_xxx` + `underscore_prefix: true` + engine `gigaam` →
  `_dir_xxx_gigaam.html`) — the reported `_xxx.html` collapse did **not**
  reproduce on this branch under any combination tried. This means either:
  - the bug lives in a code path or config combination not yet tried
    (candidates: `--refresh`, `--cleanup`'s parallel dir-name derivation at
    [main.py:142-146](../src/asr_crawler/main.py#L142), a directory nested
    more than one level deep, `processing_mode: per_step`, an engine name that
    is itself a substring of the directory name, or a stale result left over
    from a config change since there is no directory-level equivalent of
    `Cleaner.clean_other_formats` to remove it), or
  - the report is from a deployed version that predates
    [[EPIC-059]]/[[EPIC-047]]'s directory-naming rewrite and the bug may
    already be fixed — needs confirming against the version actually running
    in production before concluding "already fixed".
- Whatever the exact trigger, `Path.stem`/`Path.with_suffix` truncate at the
  **last dot** in a name, not at underscores — so the fix, wherever the bug
  turns out to live, must not depend on directories or engine names being
  free of underscores; the acceptance criteria below pin that down with
  explicit regression coverage instead of relying on manual reasoning about
  `pathlib` semantics.

## Scope

1. **Reproduce**: build a minimal repro (directory tree + config) that
   actually yields the reported `_xxx.html`-style truncated filename. Check
   the untried candidates above first (`--refresh`, `--cleanup`, nested
   subdirectories, `processing_mode: per_step`, an engine name whose
   characters overlap with the directory name, a leftover stale-format file
   from a prior `formatter.format` change).
2. **Root-cause**: once reproduced, identify the exact line(s) responsible —
   likely a string-splitting/parsing operation that assumes a directory or
   composed filename has no more than one underscore-delimited segment, or an
   accidental double-application of `Path.stem`/`with_suffix`.
3. **Fix**: correct the identified logic so directory-name text is only ever
   concatenated (never split, parsed back, or truncated) when building the
   result filename.
4. **Regression tests**: lock down correct behavior for directory names
   containing zero, one, and multiple underscores, in leading/trailing/medial
   position, combined with `underscore_prefix: true/false` and zero/one/two
   named engines — including a directory name and an engine name that share a
   substring.
5. **Docs**: none expected beyond the epic/backlog trail unless the fix
   changes documented naming behavior in `CLAUDE.md`.

## Files to change

- `src/asr_crawler/main.py` — wherever the root cause lands (candidates:
  `dir_base` construction, `output_path`, `run_cleanup`'s dir-prefix loop).
- `src/asr_crawler/pipeline/formatter.py` / `pipeline/cleaner.py` — only if the
  root cause is in format conversion or stale-format cleanup rather than
  initial filename construction.
- Tests — see below.
- `tasks/backlog.md` — section for this epic added when implementation starts.

## Acceptance Criteria

- [ ] A documented, runnable repro exists showing the exact conditions that
  produce the reported bug (or, if it cannot be reproduced on the current
  `main`, an explicit note of that plus which historical version/commit does
  reproduce it).
- [ ] For every directory name in `{dir_xxx, _xxx, a_b_c, dir_, dir_xxx_,
  __dir__xxx}` × `underscore_prefix ∈ {true, false}` × engines `∈ {none, one
  named engine, two named engines, an engine whose name is a substring of the
  directory name}`, the written directory result's filename contains the
  full, unmodified directory name, the correct prefix, and the correct engine
  label — no segment is ever dropped or truncated.
- [ ] Same guarantee holds for `--refresh` and after `--cleanup` (cleanup
  removes exactly the files a matching write would have produced — no
  under- or over-matching).
- [ ] Fix is behavior-neutral for directory names without underscores (no
  regression in `test_dir_rebuild.py`, `test_dir_concat.py`,
  `test_multi_engine.py`, `test_output_format.py`).
- [ ] Full suite green.

## Tests

- `tests/test_pipeline/test_dir_rebuild.py` or a new
  `tests/test_pipeline/test_dir_naming.py`: parametrized end-to-end run over
  the directory-name × `underscore_prefix` × engines matrix above, asserting
  the exact expected filename is the one written (not just that *a* file with
  the right content exists).
- A dedicated unit test for whichever function turns out to be the root
  cause, isolating the string manipulation from the rest of the pipeline.

## Out of Scope

- Renaming or migrating already-mis-named result files left behind by a
  previous buggy run — an operator concern, same as other pre-fix leftovers
  noted in `CLAUDE.md`.
- Any change to the naming *scheme* itself (`_<dirname>_<engine>.<ext>`) —
  this epic fixes a construction bug, not the convention.
