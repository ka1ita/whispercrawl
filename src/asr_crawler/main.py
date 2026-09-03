"""CLI entry point for asr-crawler."""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from asr_crawler.config import Config, engine_label, load_config
from asr_crawler.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _pick_summary_input(
    summarize_source: str,
    transcript: str,
    fixed_text: "str | None",
    label: str,
) -> str:
    if summarize_source == "original":
        return transcript
    if fixed_text is not None:
        return fixed_text
    logger.warning("Post-processed text unavailable for %s, falling back to original transcript", label)
    return transcript


def output_path(base: Path, suffix: str, fmt: str) -> Path:
    if fmt == "html":
        ext = ".html"
    elif fmt == "md":
        ext = ".md"
    else:
        ext = ".txt"
    return base.with_name(base.stem + suffix + ext)


def render_output(text: str, fmt: str) -> str:
    if fmt != "html":
        return text
    from html import escape
    return (
        "<!DOCTYPE html>\n<html>\n"
        '<head><meta charset="utf-8"></head>\n'
        f"<body><pre>{escape(text)}</pre>\n</body>\n</html>"
    )


def run_errors(config: Config) -> int:
    """Print failures recorded in the processing index. Returns a process exit
    code: non-zero when at least one error is outstanding, zero otherwise."""
    from asr_crawler.state import ProcessingState, default_state_path

    state_path = config.state.path or default_state_path(config.watch_dir)
    if not Path(state_path).exists():
        logger.info("No processing index at %s — nothing recorded yet.", state_path)
        return 0

    with ProcessingState.open(state_path) as state:
        errors = state.get_errors()

    if not errors:
        logger.info("No outstanding errors in the processing index.")
        return 0

    from itertools import groupby

    lines: list[str] = []
    for path, group in groupby(errors, key=lambda e: e.path):
        rows = list(group)
        is_dir = any(r.scope == "dir" for r in rows)
        lines.append(f"{path}{'  (directory)' if is_dir else ''}")
        for r in rows:
            tag = f"[{r.engine}] " if r.engine else ""
            first_line = next((ln for ln in r.message.strip().splitlines() if ln.strip()), r.message)
            lines.append(f"    {tag}{r.step:<14} {first_line}")

    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        # redirected stdout on Windows falls back to the locale codec — write
        # the bytes directly so Cyrillic paths survive a pipe / cron capture.
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 1


def run_cleanup(config: Config, dry_run: bool = False) -> None:
    """Delete the consolidated result files this version writes under watch_dir,
    and empty the processing index, without running the pipeline.

    Pre-047 sidecars (``_fix`` / ``_sum`` / ``_all`` / ``_concat``) and
    ``_err.txt`` files are left untouched — remove those by hand when upgrading
    an old catalog (EPIC-052).
    """
    _result_exts = (".txt", ".md", ".html")
    elabels = [engine_label(e.name) for e in config.transcription.engines]
    removed = 0

    def _rm(path: Path) -> None:
        nonlocal removed
        if not path.exists():
            return
        if dry_run:
            logger.info("Would clean: %s", path)
        else:
            path.unlink()
            logger.info("Cleaned: %s", path)
        removed += 1

    media = [
        p for p in sorted(config.watch_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in config.extensions
    ]

    # Per-file consolidated result, one per ASR engine, any formatter extension.
    for media_path in media:
        for label in elabels:
            for ext in _result_exts:
                _rm(media_path.with_name(media_path.stem + label + ext))

    # Per-directory consolidated result, alongside the media files.
    dir_prefix = "_" if config.dir_summarization.underscore_prefix else ""
    for dir_path in sorted({p.parent for p in media}):
        for label in elabels:
            for ext in _result_exts:
                _rm(dir_path / (dir_prefix + dir_path.name + label + ext))

    from asr_crawler.state import default_state_path
    state_path = config.state.path or default_state_path(config.watch_dir)
    if dry_run:
        logger.info("Would clear processing index: %s", state_path)
    elif Path(state_path).exists():
        from asr_crawler.state import ProcessingState
        with ProcessingState.open(state_path) as st:
            st.clear()
        logger.info("Cleared processing index: %s", state_path)

    if removed == 0:
        logger.info("No output files found in %s", config.watch_dir)


def run_pipeline(
    config: Config, dry_run: bool = False, cleanup: bool = False, refresh: bool = False
) -> None:
    """Execute the full pipeline for all matching files.

    ``refresh`` re-runs every step downstream of ASR (post-process, summarize,
    per-directory concat/summary, format) from the transcript text stored in the
    processing index — no whisper call.
    """
    from asr_crawler.state import NullState, open_state

    if dry_run:
        state = NullState()
    else:
        # config.state.path is always resolved by load_config; watch_dir enables
        # the one-time migration of a legacy <watch_dir>/.whispercrawl/state.db.
        state = open_state(config.state.path, config.watch_dir, watch_dir=config.watch_dir)
    try:
        _run_pipeline(config, state, dry_run, cleanup, refresh)
    finally:
        state.close()


def _run_pipeline(config: Config, state, dry_run: bool, cleanup: bool, refresh: bool = False) -> None:
    from asr_crawler.file_walker import iter_media_files
    from asr_crawler.pipeline.cleaner import Cleaner
    from asr_crawler.pipeline.composer import compose
    from asr_crawler.pipeline.formatter import Formatter
    from asr_crawler.pipeline.postprocessor import PostProcessor, PostProcessingError
    from asr_crawler.pipeline.summarizer import Summarizer, SummarizationError
    from asr_crawler.pipeline.transcriber import Transcriber, TranscriptionError
    from asr_crawler.utils.service_logger import ServiceLogger

    # Failures are recorded in the processing index (an ``errors`` row +
    # status='error'); nothing is written beside the audio. On ``--dry-run``
    # ``state`` is a NullState and these calls are no-ops.

    def _rel_dir(p: Path) -> str:
        try:
            return str(p.relative_to(config.watch_dir))
        except ValueError:
            return str(p)

    def _report_error(
        rel: str,
        step: str,
        engine: str,
        message: str,
        *,
        scope: str = "file",
        mtime: "float | None" = None,
        size: "int | None" = None,
    ) -> None:
        state.record_error(
            rel, step, message, engine=engine, scope=scope, mtime=mtime, size=size
        )

    engines = config.transcription.engines
    # EPIC-056 — max engine /asr calls in flight at once. Never parallelise the
    # --refresh path (no HTTP call) or a single-engine run (nothing to overlap).
    concurrency = 1 if refresh else config.transcription.concurrency
    files = list(iter_media_files(
        config.watch_dir,
        config.extensions,
        config.transcription.output_suffix,
        config.rescan,
        config.formatter.format,
        config.skip_marker,
        config.max_age_days,
        state,
        ignore_processed=refresh,
        engine_labels=[engine_label(e.name) for e in engines],
    ))

    if config.max_files_per_run is not None and len(files) > config.max_files_per_run:
        total = len(files)
        files = files[: config.max_files_per_run]
        logger.info(
            "Processing %d of %d pending files; %d remain for the next run",
            len(files), total, total - len(files),
        )

    fmt = config.formatter.format
    cleaner = Cleaner(
        fmt,
        engine_labels=[engine_label(e.name) for e in engines],
    )

    if dry_run:
        if not files:
            logger.info("No files to process in %s", config.watch_dir)
        for f in files:
            logger.info("Would process: %s", f)
            if config.rescan:
                cleaner.clean_other_formats(f, dry_run=True)
        return

    formatter = Formatter(
        fmt if config.formatter.enabled else "txt",
        speaker_style=config.formatter.speaker_style,
        text_placement=config.formatter.text_placement,
    )

    def _record(rel: str, fst, status: str, detail: str = "") -> None:
        if fst is not None:
            state.mark(rel, status, fst.st_mtime, fst.st_size, detail)

    _log_base = Path(config.logging.log_dir) if config.logging.log_dir else config.watch_dir / "logs"
    with ServiceLogger(config.logging, watch_dir=config.watch_dir) as svc_log:
        transcribers = {
            eng.name: Transcriber(
                eng,
                svc_log,
                config.logging.diarize_log,
                diarize_dir=(_log_base / "diarize" / eng.name) if eng.name else (_log_base / "diarize"),
                watch_dir=config.watch_dir,
            )
            for eng in engines
        }
        postprocessor = (
            PostProcessor(config.postprocessing, config.postprocessing.regex_patterns, svc_log)
            if config.postprocessing.llm_enabled or config.postprocessing.regex_enabled else None
        )
        file_summarizer = (
            Summarizer(config.file_summarization, svc_log)
            if config.file_summarization.llm_enabled else None
        )
        dir_summarizer = Summarizer(config.dir_summarization, svc_log)

        # dir_path → engine → {filename: [transcript, fixed_text_or_None]}
        dir_file_texts: dict[Path, dict[str, dict[str, list]]] = {}
        all_outputs_to_format: list[Path] = []
        # file_path → {engine: success_bool} accumulated across engines
        file_engine_ok: dict[Path, dict[str, bool]] = {}
        file_meta: dict[Path, tuple] = {}   # file_path → (rel, fst)
        _headings = {
            "summary": config.result.summary_heading,
            "transcript": config.result.transcript_heading,
        }

        # ── Transcribe step (EPIC-056: engines may run concurrently) ───────────
        # Split three ways so only the HTTP call touches a worker thread:
        #   _prepare_file / _prepare_engine  — main thread, reads the index
        #   _transcribe_engine_call          — worker, pure, no index / no shared dict
        #   _apply_engine_result             — main thread, writes the index + dicts

        def _prepare_file(file_path: Path) -> list:
            """Main-thread setup for one file; returns its per-engine plan list."""
            logger.info("Processing: %s", file_path)
            rel = str(file_path.relative_to(config.watch_dir))
            try:
                fst = file_path.stat()
            except OSError:
                fst = None
            file_meta[file_path] = (rel, fst)
            file_engine_ok.setdefault(file_path, {})

            if config.rescan:
                cleaner.clean_other_formats(file_path)

            return [_prepare_engine(file_path, rel, fst, eng) for eng in engines]

        def _prepare_engine(file_path: Path, rel: str, fst, eng) -> dict:
            name = eng.name
            tag = f"{file_path} [{name}]" if name else str(file_path)

            resume_steps: set = set()
            if not config.rescan and not refresh and fst is not None:
                resume_steps = state.completed_steps(rel, fst.st_mtime, fst.st_size, name)

            stored_asr = None
            if fst is not None and (refresh or "transcribe" in resume_steps):
                stored_asr = state.get_text(rel, "asr", fst.st_mtime, fst.st_size, name)

            return {
                "name": name,
                "elabel": engine_label(name),
                "tag": tag,
                "rel": rel,
                "fst": fst,
                "resume_steps": resume_steps,
                "stored_asr": stored_asr,
            }

        def _transcribe_engine_call(file_path: Path, plan: dict) -> dict:
            """Worker-thread safe: reuse stored ASR text or perform the HTTP call.
            No index writes, no shared-dict mutation. KeyboardInterrupt / SystemExit
            propagate to the caller; every other failure is returned as a result."""
            name, tag = plan["name"], plan["tag"]
            stored_asr, resume_steps = plan["stored_asr"], plan["resume_steps"]

            if refresh:
                if stored_asr is None:
                    return {"status": "skip"}
                return {"status": "stored", "transcript": stored_asr}
            if "transcribe" in resume_steps and stored_asr is not None:
                return {"status": "stored", "transcript": stored_asr}

            try:
                transcript = transcribers[name].transcribe(file_path)
            except TranscriptionError as e:
                logger.error("Transcription failed for %s: %s", tag, e)
                return {"status": "error", "message": str(e)}
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:  # noqa: BLE001 — any failure must not abort the run
                logger.exception("Transcription failed for %s", tag)
                return {"status": "error", "message": repr(e)}
            return {"status": "called", "transcript": transcript}

        def _run_transcribe_calls(flat: list) -> list:
            """Run ``_transcribe_engine_call`` for every (file_path, plan) pair,
            up to ``concurrency`` at once. Sequential (no pool) when concurrency is
            1 or there is nothing to overlap."""
            if concurrency <= 1 or len(flat) <= 1:
                return [_transcribe_engine_call(fp, p) for fp, p in flat]
            results: list = [None] * len(flat)
            ex = ThreadPoolExecutor(max_workers=min(concurrency, len(flat)))
            futures = {ex.submit(_transcribe_engine_call, fp, p): i
                       for i, (fp, p) in enumerate(flat)}
            try:
                for fut in as_completed(futures):
                    results[futures[fut]] = fut.result()
            except (KeyboardInterrupt, SystemExit):
                ex.shutdown(wait=False, cancel_futures=True)
                raise
            ex.shutdown(wait=True)
            return results

        def _apply_engine_result(file_path: Path, plan: dict, result: dict) -> "dict | None":
            """Main-thread: apply one engine's transcribe result — index writes,
            error recording, shared-dict population. Returns a context dict when the
            engine produced a transcript, else None."""
            name, tag = plan["name"], plan["tag"]
            rel, fst = plan["rel"], plan["fst"]
            status = result["status"]

            if status == "skip":
                logger.info("Refresh: no stored ASR text for %s — skipping this engine", tag)
                return None
            if status == "error":
                _report_error(
                    rel, "transcribe", name, result["message"],
                    mtime=fst.st_mtime if fst is not None else None,
                    size=fst.st_size if fst is not None else None,
                )
                file_engine_ok[file_path][name] = False
                return None

            transcript = result["transcript"]
            if status == "stored":
                logger.info(
                    "Refreshing from stored ASR text: %s" if refresh
                    else "Resuming: using stored ASR transcript for %s",
                    tag,
                )
            else:  # "called"
                logger.info("Transcribed: %s", tag)
                if fst is not None:
                    state.mark_step(rel, "transcribe", fst.st_mtime, fst.st_size, name)
                    state.save_text(rel, "asr", transcript, fst.st_mtime, fst.st_size, name)

            dir_file_texts.setdefault(file_path.parent, {}).setdefault(name, {})[file_path.name] = [
                transcript, None
            ]
            return {
                "engine": name,
                "elabel": plan["elabel"],
                "rel": rel,
                "fst": fst,
                "resume_steps": plan["resume_steps"],
                "transcript": transcript,
                "fixed_text": None,
                "summary": "",
                "success": True,
            }

        def _apply_file(file_path: Path, plans: list, results: list) -> list:
            """Main-thread: apply every engine result for one file; returns the
            context dicts for engines that produced a transcript."""
            contexts = []
            for plan, result in zip(plans, results):
                ctx = _apply_engine_result(file_path, plan, result)
                if ctx is not None:
                    contexts.append(ctx)
            return contexts

        def _postprocess_one(file_path: Path, ctx: dict) -> None:
            if not postprocessor:
                return
            rel, fst, resume_steps, eng = ctx["rel"], ctx["fst"], ctx["resume_steps"], ctx["engine"]
            transcript = ctx["transcript"]
            stored_fixed = (
                state.get_text(rel, "fixed", fst.st_mtime, fst.st_size, eng)
                if fst is not None and "postprocess" in resume_steps else None
            )
            if stored_fixed is not None:
                ctx["fixed_text"] = stored_fixed
                dir_file_texts[file_path.parent][eng][file_path.name][1] = stored_fixed
                logger.info("Resuming: using stored post-processed text for %s", file_path)
                return

            try:
                fixed_text = postprocessor.process(transcript, source_path=file_path)
            except PostProcessingError as e:
                logger.error("Post-processing failed for %s: %s", file_path, e)
                _report_error(
                    rel, "postprocess", eng, str(e),
                    mtime=fst.st_mtime if fst is not None else None,
                    size=fst.st_size if fst is not None else None,
                )
                ctx["success"] = False
                return
            except (KeyboardInterrupt, SystemExit):
                _record(rel, fst, "partial", "interrupted mid-pipeline")
                raise
            except Exception as e:  # noqa: BLE001 — any failure must not abort the run
                logger.exception("Post-processing failed for %s", file_path)
                _report_error(
                    rel, "postprocess", eng, repr(e),
                    mtime=fst.st_mtime if fst is not None else None,
                    size=fst.st_size if fst is not None else None,
                )
                ctx["success"] = False
                return

            ctx["fixed_text"] = fixed_text
            dir_file_texts[file_path.parent][eng][file_path.name][1] = fixed_text
            logger.info("Post-processed: %s", file_path)
            if fst is not None:
                state.mark_step(rel, "postprocess", fst.st_mtime, fst.st_size, eng)
                state.save_text(rel, "fixed", fixed_text, fst.st_mtime, fst.st_size, eng)

        def _summarize_one(file_path: Path, ctx: dict) -> None:
            if not file_summarizer:
                return
            rel, fst, eng = ctx["rel"], ctx["fst"], ctx["engine"]
            transcript, fixed_text = ctx["transcript"], ctx["fixed_text"]
            summary_input = _pick_summary_input(
                config.file_summarization.summarize_source,
                transcript,
                fixed_text,
                file_path.name,
            )
            try:
                summary = file_summarizer.summarize_file(summary_input, file=file_path.name)
            except SummarizationError as e:
                logger.error("File summarization failed for %s: %s", file_path, e)
                _report_error(
                    rel, "file_summarize", eng, str(e),
                    mtime=fst.st_mtime if fst is not None else None,
                    size=fst.st_size if fst is not None else None,
                )
                ctx["success"] = False
                return
            except (KeyboardInterrupt, SystemExit):
                _record(rel, fst, "partial", "interrupted mid-pipeline")
                raise
            except Exception as e:  # noqa: BLE001 — any failure must not abort the run
                logger.exception("File summarization failed for %s", file_path)
                _report_error(
                    rel, "file_summarize", eng, repr(e),
                    mtime=fst.st_mtime if fst is not None else None,
                    size=fst.st_size if fst is not None else None,
                )
                ctx["success"] = False
                return

            ctx["summary"] = summary
            logger.info("Summarized: %s", file_path)
            if fst is not None:
                state.mark_step(rel, "file_summarize", fst.st_mtime, fst.st_size, eng)

        def _finalize_one(file_path: Path, ctx: dict) -> None:
            success = ctx["success"]
            rel, fst, eng = ctx["rel"], ctx["fst"], ctx["engine"]
            if success:
                try:
                    body = ctx["fixed_text"] if ctx["fixed_text"] is not None else ctx["transcript"]
                    document = compose(
                        config.result.file_sections,
                        {"summary": ctx["summary"], "transcript": body},
                        _headings,
                        config.result,
                    )
                    result_path = output_path(
                        file_path, ctx["elabel"] + config.transcription.output_suffix, "txt"
                    )
                    result_path.write_text(document, encoding="utf-8")
                except (KeyboardInterrupt, SystemExit):
                    _record(rel, fst, "partial", "interrupted mid-pipeline")
                    raise
                except Exception as e:  # noqa: BLE001 — any failure must not abort the run
                    logger.exception("Writing result failed for %s", file_path)
                    _report_error(
                        rel, "finalize", eng, repr(e),
                        mtime=fst.st_mtime if fst is not None else None,
                        size=fst.st_size if fst is not None else None,
                    )
                    file_engine_ok[file_path][eng] = False
                    return
                all_outputs_to_format.append(result_path)
                logger.info("Result written: %s", result_path)
                if refresh and fst is not None:
                    for _s in ("transcribe", "postprocess", "file_summarize"):
                        state.mark_step(rel, _s, fst.st_mtime, fst.st_size, eng)
                state.clear_errors(rel, engine=eng, scope="file")
            file_engine_ok[file_path][eng] = success

        def _finalize_file(file_path: Path) -> None:
            rel, fst = file_meta[file_path]
            results = file_engine_ok.get(file_path, {})
            if not results:
                # nothing ran for any engine (e.g. --refresh with no stored text) —
                # leave the index untouched
                return
            all_ok = all(results.values())
            if cleanup:
                cleaner.clean(file_path, all_ok)
            failed = [e or "(default)" for e, ok in results.items() if not ok]
            _record(rel, fst, "done" if all_ok else "error",
                    "" if all_ok else f"pipeline step failed for engine(s): {', '.join(failed)}")

        def _unexpected_file_failure(file_path: Path) -> None:
            """Last-resort guard: an exception escaped a step's own handling.
            Record the file as errored and move on rather than abort the run."""
            logger.exception("Unexpected failure processing %s", file_path)
            rel, fst = file_meta.get(file_path, (str(file_path), None))
            file_engine_ok.setdefault(file_path, {}).setdefault("", False)
            _record(rel, fst, "error", "unexpected failure during processing")

        def _record_all_partial(file_paths) -> None:
            for fp in file_paths:
                rel_fst = file_meta.get(fp)
                if rel_fst is not None:
                    _record(rel_fst[0], rel_fst[1], "partial", "interrupted mid-pipeline")

        if config.processing_mode == "per_step":
            # Transcribe phase: one bounded pool over every (file, engine) pair, so
            # at most `concurrency` /asr calls are ever in flight across the phase.
            prepared: list = []  # (file_path, plans)
            for file_path in files:
                try:
                    prepared.append((file_path, _prepare_file(file_path)))
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:  # noqa: BLE001
                    _unexpected_file_failure(file_path)
            flat = [(fp, plan) for fp, plans in prepared for plan in plans]
            try:
                flat_results = _run_transcribe_calls(flat)
            except (KeyboardInterrupt, SystemExit):
                _record_all_partial(fp for fp, _ in prepared)
                raise

            pairs: list = []
            cursor = 0
            for file_path, plans in prepared:
                results = flat_results[cursor:cursor + len(plans)]
                cursor += len(plans)
                try:
                    for ctx in _apply_file(file_path, plans, results):
                        pairs.append((file_path, ctx))
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:  # noqa: BLE001
                    _unexpected_file_failure(file_path)

            for step_fn in (_postprocess_one, _summarize_one, _finalize_one):
                for file_path, ctx in pairs:
                    try:
                        step_fn(file_path, ctx)
                    except (KeyboardInterrupt, SystemExit):
                        raise
                    except Exception:  # noqa: BLE001
                        _unexpected_file_failure(file_path)
                        ctx["success"] = False
            for file_path in files:
                if file_path in file_meta:
                    _finalize_file(file_path)
        else:
            for file_path in files:
                try:
                    plans = _prepare_file(file_path)
                    try:
                        results = _run_transcribe_calls([(file_path, p) for p in plans])
                    except (KeyboardInterrupt, SystemExit):
                        _record_all_partial([file_path])
                        raise
                    for ctx in _apply_file(file_path, plans, results):
                        _postprocess_one(file_path, ctx)
                        _summarize_one(file_path, ctx)
                        _finalize_one(file_path, ctx)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:  # noqa: BLE001
                    _unexpected_file_failure(file_path)
                if file_path in file_meta:
                    _finalize_file(file_path)

        prefix = "_" if config.dir_summarization.underscore_prefix else ""
        for dir_path in sorted(dir_file_texts):
            dir_rel = _rel_dir(dir_path)
            for eng_name in sorted(dir_file_texts[dir_path]):
                elabel = engine_label(eng_name)
                dir_base = dir_path / (prefix + dir_path.name + elabel)
                try:
                    selected = {
                        name: _pick_summary_input(
                            config.dir_summarization.concat_source,
                            entry[0],
                            entry[1],
                            name,
                        )
                        for name, entry in dir_file_texts[dir_path][eng_name].items()
                    }
                    combined = dir_summarizer.concat_transcriptions(selected)

                    dir_summary = ""
                    if config.dir_summarization.llm_enabled:
                        dir_summary = dir_summarizer.summarize_file(combined, file=str(dir_path.name))

                    document = compose(
                        config.result.dir_sections,
                        {"summary": dir_summary, "transcript": combined},
                        _headings,
                        config.result,
                    )
                    dir_result_path = output_path(dir_base, "", "txt")
                    dir_result_path.write_text(document, encoding="utf-8")
                    all_outputs_to_format.append(dir_result_path)
                    logger.info("Directory result written: %s", dir_result_path)

                    state.clear_errors(dir_rel, engine=eng_name, scope="dir")
                except SummarizationError as e:
                    logger.error("Directory summarization failed for %s: %s", dir_path, e)
                    _report_error(dir_rel, "dir_summarize", eng_name, str(e), scope="dir")
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:  # noqa: BLE001 — one bad directory must not abort the rest
                    logger.exception("Directory result failed for %s", dir_path)
                    _report_error(dir_rel, "dir_finalize", eng_name, repr(e), scope="dir")
        dir_file_texts.clear()

        outstanding = state.get_errors()
        if outstanding:
            n_files = len({e.path for e in outstanding if e.scope == "file"})
            n_dirs = sum(1 for e in outstanding if e.scope == "dir")
            logger.warning(
                "%d file(s) and %d directory step(s) finished with errors; "
                "run 'asr-crawler --errors' for details",
                n_files, n_dirs,
            )

        for path in all_outputs_to_format:
            if not path.exists():
                continue
            try:
                formatter.format_file(path)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:  # noqa: BLE001 — one bad file must not skip the rest
                logger.exception("Formatting failed for %s", path)
                rel = _rel_dir(path)
                _report_error(rel, "format", "", repr(e), scope="file")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="asr-crawler", description="asr-crawler — audio/video transcription pipeline"
    )
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Path to config file")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Log files that would be processed without processing them")
    parser.add_argument("--cleanup", action="store_true", help="Delete output files under watch_dir without running the pipeline")
    parser.add_argument(
        "--errors",
        action="store_true",
        help="List pipeline failures recorded in the processing index and exit "
        "non-zero if any are outstanding.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run post-processing, summarization, and formatting from the transcript "
        "text stored in the processing index — no whisper call.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.logging)

    if args.cleanup and not args.once:
        run_cleanup(config, dry_run=args.dry_run)
        return

    if args.errors:
        raise SystemExit(run_errors(config))

    if args.refresh:
        run_pipeline(config, refresh=True, cleanup=args.cleanup)
        return

    if args.once or args.dry_run:
        run_pipeline(config, dry_run=args.dry_run, cleanup=args.cleanup)
        return

    from asr_crawler.scheduler import start_scheduler
    start_scheduler(config)


if __name__ == "__main__":
    main()
