"""CLI entry point for whispercrawl."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from whispercrawl.config import Config, engine_label, load_config
from whispercrawl.utils.logging_setup import setup_logging

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


def _write_error(file_path: Path, error_suffix: str, message: str) -> None:
    err_path = output_path(file_path, error_suffix, "txt")
    err_path.write_text(message, encoding="utf-8")


def run_cleanup(config: Config, dry_run: bool = False) -> None:
    """Delete pipeline output files under watch_dir without running the pipeline."""
    fmt = config.formatter.format
    targets = config.cleanup.targets
    elabels = [engine_label(e.name) for e in (config.transcription.engines or [config.transcription])]
    removed = 0

    for media_path in sorted(config.watch_dir.rglob("*")):
        if not media_path.is_file():
            continue
        if media_path.suffix.lower() not in config.extensions:
            continue
        for label in elabels:
            for suffix in targets:
                out = (
                    media_path.with_name(media_path.stem + suffix)
                    if suffix.endswith(".json")
                    else output_path(media_path, label + suffix, fmt)
                )
                if out.exists():
                    if dry_run:
                        logger.info("Would clean: %s", out)
                    else:
                        out.unlink()
                        logger.info("Cleaned: %s", out)
                    removed += 1

    # Also remove per-directory summary files found alongside media files
    dirs_seen: set[Path] = {
        p.parent
        for p in config.watch_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in config.extensions
    }
    dir_prefix = "_" if config.dir_summarization.underscore_prefix else ""
    for dir_path in sorted(dirs_seen):
        for label in elabels:
            for suffix in targets:
                if suffix.endswith(".json"):
                    dir_sum = dir_path / (dir_path.name + suffix)
                else:
                    dir_base = dir_path / (dir_prefix + dir_path.name + label)
                    dir_sum = output_path(dir_base, suffix, fmt)
                if not dir_sum.exists():
                    continue
                if dry_run:
                    logger.info("Would clean: %s", dir_sum)
                else:
                    dir_sum.unlink()
                    logger.info("Cleaned: %s", dir_sum)
                removed += 1

    # Remove all error files unconditionally (always written as .txt)
    err_suffixes = {
        config.transcription.error_suffix,
        config.postprocessing.error_suffix,
        config.file_summarization.error_suffix,
        config.dir_summarization.error_suffix,
    }
    for suffix in sorted(err_suffixes):
        for err_file in sorted(config.watch_dir.rglob(f"*{suffix}.txt")):
            if dry_run:
                logger.info("Would clean: %s", err_file)
            else:
                err_file.unlink()
                logger.info("Cleaned: %s", err_file)
            removed += 1

    if config.state.enabled:
        from whispercrawl.state import default_state_path
        state_path = config.state.path or default_state_path(config.watch_dir)  # load_config always resolves .path
        if dry_run:
            logger.info("Would clear processing index: %s", state_path)
        elif Path(state_path).exists():
            from whispercrawl.state import ProcessingState
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
    processing index — no whisper call. It requires the index and text storage
    to be enabled.
    """
    from whispercrawl.state import NullState, open_state

    if refresh and not (config.state.enabled and config.state.store_text):
        logger.error(
            "--refresh needs state.enabled: true and state.store_text: true "
            "(the raw transcript is read back from the index)."
        )
        return

    if dry_run:
        state = NullState()
    else:
        # config.state.path is always resolved by load_config; watch_dir enables
        # the one-time migration of a legacy <watch_dir>/.whispercrawl/state.db.
        state = open_state(
            config.state.enabled, config.state.path, config.watch_dir, watch_dir=config.watch_dir
        )
    try:
        _run_pipeline(config, state, dry_run, cleanup, refresh)
    finally:
        state.close()


def _run_pipeline(config: Config, state, dry_run: bool, cleanup: bool, refresh: bool = False) -> None:
    from whispercrawl.file_walker import iter_media_files
    from whispercrawl.pipeline.cleaner import Cleaner
    from whispercrawl.pipeline.composer import compose
    from whispercrawl.pipeline.formatter import Formatter
    from whispercrawl.pipeline.postprocessor import PostProcessor, PostProcessingError
    from whispercrawl.pipeline.summarizer import Summarizer, SummarizationError
    from whispercrawl.pipeline.transcriber import Transcriber, TranscriptionError
    from whispercrawl.utils.service_logger import ServiceLogger

    _engines = config.transcription.engines or [config.transcription]
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
        engine_labels=[engine_label(e.name) for e in _engines],
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
        config.cleanup, fmt,
        engine_labels=[engine_label(e.name) for e in _engines],
    )
    _rescan_labels = [s for s in config.cleanup.targets if not s.endswith(".json")]

    if dry_run:
        if not files:
            logger.info("No files to process in %s", config.watch_dir)
        for f in files:
            logger.info("Would process: %s", f)
            if config.rescan:
                cleaner.clean_other_formats(f, _rescan_labels, dry_run=True)
        return

    formatter = Formatter(
        fmt if config.formatter.enabled else "txt",
        speaker_style=config.formatter.speaker_style,
        text_placement=config.formatter.text_placement,
    )

    def _record(rel: str, fst, status: str, detail: str = "") -> None:
        if fst is not None:
            state.mark(rel, status, fst.st_mtime, fst.st_size, detail)


    engines = config.transcription.engines or [config.transcription]

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

        def _transcribe_file(file_path: Path) -> list:
            """Run/resume the transcribe step for every engine. Returns one context
            dict per engine that produced a transcript (a failed / skipped engine is
            simply absent from the list)."""
            logger.info("Processing: %s", file_path)
            rel = str(file_path.relative_to(config.watch_dir))
            try:
                fst = file_path.stat()
            except OSError:
                fst = None
            file_meta[file_path] = (rel, fst)
            file_engine_ok.setdefault(file_path, {})

            if config.rescan:
                cleaner.clean_other_formats(file_path, _rescan_labels)

            contexts = []
            for eng in engines:
                ctx = _transcribe_engine(file_path, rel, fst, eng)
                if ctx is not None:
                    contexts.append(ctx)
            return contexts

        def _transcribe_engine(file_path: Path, rel: str, fst, eng) -> "dict | None":
            name = eng.name
            elabel = engine_label(name)
            tag = f"{file_path} [{name}]" if name else str(file_path)

            resume_steps: set = set()
            if not config.rescan and not refresh and fst is not None:
                resume_steps = state.completed_steps(rel, fst.st_mtime, fst.st_size, name)

            stored_asr = None
            if fst is not None and (refresh or "transcribe" in resume_steps):
                stored_asr = state.get_text(rel, "asr", fst.st_mtime, fst.st_size, name)

            if refresh:
                if stored_asr is None:
                    logger.info("Refresh: no stored ASR text for %s — skipping this engine", tag)
                    return None
                transcript = stored_asr
                logger.info("Refreshing from stored ASR text: %s", tag)
            elif "transcribe" in resume_steps and stored_asr is not None:
                transcript = stored_asr
                logger.info("Resuming: using stored ASR transcript for %s", tag)
            else:
                try:
                    transcript = transcribers[name].transcribe(file_path)
                except TranscriptionError as e:
                    logger.error("Transcription failed for %s: %s", tag, e)
                    _write_error(file_path, elabel + eng.error_suffix, str(e))
                    file_engine_ok[file_path][name] = False
                    return None
                except (KeyboardInterrupt, SystemExit):
                    _record(rel, fst, "partial", "interrupted mid-pipeline")
                    raise

                logger.info("Transcribed: %s", tag)
                if fst is not None:
                    state.mark_step(rel, "transcribe", fst.st_mtime, fst.st_size, name)
                    if config.state.store_text:
                        state.save_text(rel, "asr", transcript, fst.st_mtime, fst.st_size, name)

            dir_file_texts.setdefault(file_path.parent, {}).setdefault(name, {})[file_path.name] = [
                transcript, None
            ]
            return {
                "engine": name,
                "elabel": elabel,
                "rel": rel,
                "fst": fst,
                "resume_steps": resume_steps,
                "transcript": transcript,
                "fixed_text": None,
                "summary": "",
                "success": True,
            }

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
                _write_error(file_path, ctx["elabel"] + config.postprocessing.error_suffix, str(e))
                ctx["success"] = False
                return

            ctx["fixed_text"] = fixed_text
            dir_file_texts[file_path.parent][eng][file_path.name][1] = fixed_text
            logger.info("Post-processed: %s", file_path)
            if fst is not None:
                state.mark_step(rel, "postprocess", fst.st_mtime, fst.st_size, eng)
                if config.state.store_text:
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
                _write_error(file_path, ctx["elabel"] + config.file_summarization.error_suffix, str(e))
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
                all_outputs_to_format.append(result_path)
                logger.info("Result written: %s", result_path)
                if refresh and fst is not None:
                    for _s in ("transcribe", "postprocess", "file_summarize"):
                        state.mark_step(rel, _s, fst.st_mtime, fst.st_size, eng)
            file_engine_ok[file_path][eng] = success

        def _finalize_file(file_path: Path) -> None:
            rel, fst = file_meta[file_path]
            results = file_engine_ok.get(file_path, {})
            if not results:
                # nothing ran for any engine (e.g. --refresh with no stored text) —
                # leave the index untouched and write no _err.txt
                return
            all_ok = all(results.values())
            if cleanup:
                cleaner.clean(file_path, all_ok)
            if all_ok:
                for eng in engines:
                    err_path = output_path(
                        file_path, engine_label(eng.name) + config.transcription.error_suffix, "txt"
                    )
                    if err_path.exists():
                        err_path.unlink()
                        logger.debug("Removed stale error file: %s", err_path)
            failed = [e or "(default)" for e, ok in results.items() if not ok]
            _record(rel, fst, "done" if all_ok else "error",
                    "" if all_ok else f"pipeline step failed for engine(s): {', '.join(failed)}")

        if config.processing_mode == "per_step":
            pairs: list = []
            for file_path in files:
                for ctx in _transcribe_file(file_path):
                    pairs.append((file_path, ctx))
            for file_path, ctx in pairs:
                _postprocess_one(file_path, ctx)
            for file_path, ctx in pairs:
                _summarize_one(file_path, ctx)
            for file_path, ctx in pairs:
                _finalize_one(file_path, ctx)
            for file_path in files:
                if file_path in file_meta:
                    _finalize_file(file_path)
        else:
            for file_path in files:
                for ctx in _transcribe_file(file_path):
                    _postprocess_one(file_path, ctx)
                    _summarize_one(file_path, ctx)
                    _finalize_one(file_path, ctx)
                if file_path in file_meta:
                    _finalize_file(file_path)

        prefix = "_" if config.dir_summarization.underscore_prefix else ""
        for dir_path in sorted(dir_file_texts):
            for eng_name in sorted(dir_file_texts[dir_path]):
                elabel = engine_label(eng_name)
                dir_base = dir_path / (prefix + dir_path.name + elabel)
                dir_err_path = output_path(dir_base, config.dir_summarization.error_suffix, "txt")
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

                    if dir_err_path.exists():
                        dir_err_path.unlink()
                        logger.debug("Removed stale error file: %s", dir_err_path)
                except SummarizationError as e:
                    logger.error("Directory summarization failed for %s: %s", dir_path, e)
                    dir_err_path.write_text(str(e), encoding="utf-8")
        dir_file_texts.clear()

        for path in all_outputs_to_format:
            if path.exists():
                formatter.format_file(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="whispercrawl — audio/video transcription pipeline")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Path to config file")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Log files that would be processed without processing them")
    parser.add_argument("--cleanup", action="store_true", help="Delete output files under watch_dir without running the pipeline")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run post-processing, summarization, and formatting from the transcript "
        "text stored in the processing index — no whisper call. Needs state.enabled + state.store_text.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.logging)

    if args.cleanup and not args.once:
        run_cleanup(config, dry_run=args.dry_run)
        return

    if args.refresh:
        run_pipeline(config, refresh=True, cleanup=args.cleanup)
        return

    if args.once or args.dry_run:
        run_pipeline(config, dry_run=args.dry_run, cleanup=args.cleanup)
        return

    from whispercrawl.scheduler import start_scheduler
    start_scheduler(config)


if __name__ == "__main__":
    main()
