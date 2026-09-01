"""CLI entry point for whispercrawl."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from whispercrawl.config import Config, load_config
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
    removed = 0

    for media_path in sorted(config.watch_dir.rglob("*")):
        if not media_path.is_file():
            continue
        if media_path.suffix.lower() not in config.extensions:
            continue
        for suffix in targets:
            out = (
                media_path.with_name(media_path.stem + suffix)
                if suffix.endswith(".json")
                else output_path(media_path, suffix, fmt)
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
    concat_suffix = config.dir_summarization.concat_suffix
    for dir_path in sorted(dirs_seen):
        for suffix in targets:
            dir_base = dir_path / (dir_prefix + dir_path.name)
            if suffix.endswith(".json"):
                dir_sum = dir_path / (dir_path.name + suffix)
            elif suffix == concat_suffix:
                dir_sum = output_path(dir_base, suffix, fmt)
            else:
                dir_sum = output_path(dir_base, suffix, fmt)
            if dir_sum.exists():
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
        state_path = config.state.path or default_state_path(config.watch_dir)
        if dry_run:
            logger.info("Would clear processing index: %s", state_path)
        elif Path(state_path).exists():
            from whispercrawl.state import ProcessingState
            with ProcessingState.open(state_path) as st:
                st.clear()
            logger.info("Cleared processing index: %s", state_path)

    if removed == 0:
        logger.info("No output files found in %s", config.watch_dir)


def run_pipeline(config: Config, dry_run: bool = False, cleanup: bool = False) -> None:
    """Execute the full pipeline for all matching files."""
    from whispercrawl.state import NullState, open_state

    if dry_run:
        state = NullState()
    else:
        state = open_state(config.state.enabled, config.state.path, config.watch_dir)
    try:
        _run_pipeline(config, state, dry_run, cleanup)
    finally:
        state.close()


def _run_pipeline(config: Config, state, dry_run: bool, cleanup: bool) -> None:
    from whispercrawl.file_walker import iter_media_files
    from whispercrawl.pipeline.cleaner import Cleaner
    from whispercrawl.pipeline.formatter import Formatter
    from whispercrawl.pipeline.postprocessor import PostProcessor, PostProcessingError
    from whispercrawl.pipeline.summarizer import Summarizer, SummarizationError
    from whispercrawl.pipeline.transcriber import Transcriber, TranscriptionError
    from whispercrawl.utils.service_logger import ServiceLogger

    files = list(iter_media_files(
        config.watch_dir,
        config.extensions,
        config.transcription.output_suffix,
        config.rescan,
        config.formatter.format,
        config.skip_marker,
        config.max_age_days,
        state,
    ))

    if config.max_files_per_run is not None and len(files) > config.max_files_per_run:
        total = len(files)
        files = files[: config.max_files_per_run]
        logger.info(
            "Processing %d of %d pending files; %d remain for the next run",
            len(files), total, total - len(files),
        )

    fmt = config.formatter.format
    cleaner = Cleaner(config.cleanup, fmt)
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

    with ServiceLogger(config.logging, watch_dir=config.watch_dir) as svc_log:
        transcriber = Transcriber(config.transcription, svc_log, config.logging.diarize_log)
        postprocessor = (
            PostProcessor(config.postprocessing, config.postprocessing.regex_patterns, svc_log)
            if config.postprocessing.llm_enabled or config.postprocessing.regex_enabled else None
        )
        file_summarizer = (
            Summarizer(config.file_summarization, svc_log)
            if config.file_summarization.llm_enabled else None
        )
        dir_summarizer = Summarizer(config.dir_summarization, svc_log)

        # dir_path → {filename: [transcript, fixed_text_or_None]}
        dir_file_texts: dict[Path, dict[str, list]] = {}
        all_outputs_to_format: list[Path] = []

        def _transcribe_one(file_path: Path) -> dict:
            """Run/resume the transcribe step. Returns a per-file context dict; ctx["ok"]
            is False (with no other keys) when transcription failed and the file must be
            skipped entirely."""
            logger.info("Processing: %s", file_path)
            rel = str(file_path.relative_to(config.watch_dir))
            try:
                fst = file_path.stat()
            except OSError:
                fst = None

            if config.rescan:
                cleaner.clean_other_formats(file_path, _rescan_labels)

            resume_steps: set = set()
            if not config.rescan and fst is not None:
                resume_steps = state.completed_steps(rel, fst.st_mtime, fst.st_size)

            txt_path = output_path(file_path, config.transcription.output_suffix, "txt")

            if "transcribe" in resume_steps and txt_path.exists():
                transcript = txt_path.read_text(encoding="utf-8")
                logger.info("Resuming: transcript already present: %s", txt_path)
            else:
                try:
                    transcript = transcriber.transcribe(file_path)
                except TranscriptionError as e:
                    logger.error("Transcription failed for %s: %s", file_path, e)
                    _write_error(file_path, config.transcription.error_suffix, str(e))
                    if cleanup:
                        cleaner.clean(file_path, success=False)
                    _record(rel, fst, "error", "transcription failed")
                    return {"ok": False}
                except (KeyboardInterrupt, SystemExit):
                    _record(rel, fst, "partial", "interrupted mid-pipeline")
                    raise

                txt_path.write_text(transcript, encoding="utf-8")
                logger.info("Transcript written: %s", txt_path)
                if fst is not None:
                    state.mark_step(rel, "transcribe", fst.st_mtime, fst.st_size)

            # Track per-dir texts for concatenation step; entry is [transcript, fixed_text]
            dir_file_texts.setdefault(file_path.parent, {})[file_path.name] = [transcript, None]

            return {
                "ok": True,
                "rel": rel,
                "fst": fst,
                "resume_steps": resume_steps,
                "transcript": transcript,
                "fixed_text": None,
                "txt_path": txt_path,
                "files_to_format": [txt_path],
                "success": True,
            }

        def _postprocess_one(file_path: Path, ctx: dict) -> None:
            if not postprocessor:
                return
            rel, fst, resume_steps = ctx["rel"], ctx["fst"], ctx["resume_steps"]
            transcript, txt_path = ctx["transcript"], ctx["txt_path"]
            fix_path = output_path(file_path, config.postprocessing.output_suffix, "txt")
            resumed_postprocess = "postprocess" in resume_steps and (
                fix_path.exists() if not config.postprocessing.replace_transcription else True
            )
            if resumed_postprocess:
                if config.postprocessing.replace_transcription:
                    fixed_text = transcript
                else:
                    fixed_text = fix_path.read_text(encoding="utf-8")
                dir_file_texts[file_path.parent][file_path.name][1] = fixed_text
                if not config.postprocessing.replace_transcription:
                    ctx["files_to_format"].append(fix_path)
                logger.info("Resuming: post-processed text already present for %s", file_path)
                ctx["fixed_text"] = fixed_text
                return

            try:
                fixed_text = postprocessor.process(transcript, source_path=file_path)
                fix_path.write_text(fixed_text, encoding="utf-8")
                dir_file_texts[file_path.parent][file_path.name][1] = fixed_text
                if config.postprocessing.replace_transcription:
                    fix_path.replace(txt_path)
                    logger.info("Replaced transcript with post-processed: %s", txt_path)
                else:
                    ctx["files_to_format"].append(fix_path)
                    logger.info("Post-processed: %s", fix_path)
                if fst is not None:
                    state.mark_step(rel, "postprocess", fst.st_mtime, fst.st_size)
                ctx["fixed_text"] = fixed_text
            except PostProcessingError as e:
                logger.error("Post-processing failed for %s: %s", file_path, e)
                _write_error(file_path, config.postprocessing.error_suffix, str(e))
                ctx["success"] = False

        def _summarize_one(file_path: Path, ctx: dict) -> None:
            if not file_summarizer:
                return
            rel, fst, resume_steps = ctx["rel"], ctx["fst"], ctx["resume_steps"]
            transcript, fixed_text = ctx["transcript"], ctx["fixed_text"]
            sum_path = output_path(file_path, config.file_summarization.output_suffix, "txt")
            if "file_summarize" in resume_steps and sum_path.exists():
                ctx["files_to_format"].append(sum_path)
                logger.info("Resuming: file summary already present: %s", sum_path)
                return

            summary_input = _pick_summary_input(
                config.file_summarization.summarize_source,
                transcript,
                fixed_text,
                file_path.name,
            )
            try:
                summary = file_summarizer.summarize_file(summary_input, file=file_path.name)
                sum_path.write_text(summary, encoding="utf-8")
                ctx["files_to_format"].append(sum_path)
                logger.info("File summary written: %s", sum_path)
                if fst is not None:
                    state.mark_step(rel, "file_summarize", fst.st_mtime, fst.st_size)
            except SummarizationError as e:
                logger.error("File summarization failed for %s: %s", file_path, e)
                _write_error(file_path, config.file_summarization.error_suffix, str(e))
                ctx["success"] = False

        def _finalize_one(file_path: Path, ctx: dict) -> None:
            all_outputs_to_format.extend(ctx["files_to_format"])
            success = ctx["success"]
            if cleanup:
                cleaner.clean(file_path, success)
            if success:
                err_path = output_path(file_path, config.transcription.error_suffix, "txt")
                if err_path.exists():
                    err_path.unlink()
                    logger.debug("Removed stale error file: %s", err_path)
            _record(ctx["rel"], ctx["fst"], "done" if success else "error",
                    "" if success else "pipeline step failed")

        if config.processing_mode == "per_step":
            contexts: dict[Path, dict] = {}
            for file_path in files:
                ctx = _transcribe_one(file_path)
                if ctx["ok"]:
                    contexts[file_path] = ctx
            for file_path, ctx in contexts.items():
                _postprocess_one(file_path, ctx)
            for file_path, ctx in contexts.items():
                _summarize_one(file_path, ctx)
            for file_path, ctx in contexts.items():
                _finalize_one(file_path, ctx)
        else:
            for file_path in files:
                ctx = _transcribe_one(file_path)
                if not ctx["ok"]:
                    continue
                _postprocess_one(file_path, ctx)
                _summarize_one(file_path, ctx)
                _finalize_one(file_path, ctx)

        prefix = "_" if config.dir_summarization.underscore_prefix else ""
        for dir_path in sorted(dir_file_texts):
            dir_base = dir_path / (prefix + dir_path.name)
            dir_err_path = output_path(dir_base, config.dir_summarization.error_suffix, "txt")
            try:
                selected = {
                    name: _pick_summary_input(
                        config.dir_summarization.concat_source,
                        entry[0],
                        entry[1],
                        name,
                    )
                    for name, entry in dir_file_texts[dir_path].items()
                }
                combined = dir_summarizer.concat_transcriptions(selected)
                concat_path = dir_path / (prefix + dir_path.name + config.dir_summarization.concat_suffix + ".txt")
                concat_path.write_text(combined, encoding="utf-8")
                logger.info("Concatenated transcriptions written: %s", concat_path)
                all_outputs_to_format.append(concat_path)

                if config.dir_summarization.llm_enabled:
                    dir_summary = dir_summarizer.summarize_file(combined, file=str(dir_path.name))
                    dir_sum_path = output_path(dir_base, config.dir_summarization.output_suffix, "txt")
                    dir_sum_path.write_text(dir_summary, encoding="utf-8")
                    all_outputs_to_format.append(dir_sum_path)
                    logger.info("Directory summary written: %s", dir_sum_path)

                if dir_err_path.exists():
                    dir_err_path.unlink()
                    logger.debug("Removed stale error file: %s", dir_err_path)
            except SummarizationError as e:
                logger.error("Directory summarization failed for %s: %s", dir_path, e)
                dir_err_path.write_text(str(e), encoding="utf-8")
            finally:
                # free this directory's transcripts; peak memory stays bounded
                # by one directory (or by max_files_per_run) rather than the whole run
                dir_file_texts.pop(dir_path, None)

        for path in all_outputs_to_format:
            if path.exists():
                formatter.format_file(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="whispercrawl — audio/video transcription pipeline")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Path to config file")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Log files that would be processed without processing them")
    parser.add_argument("--cleanup", action="store_true", help="Delete output files under watch_dir without running the pipeline")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.logging)

    if args.cleanup and not args.once:
        run_cleanup(config, dry_run=args.dry_run)
        return

    if args.once or args.dry_run:
        run_pipeline(config, dry_run=args.dry_run, cleanup=args.cleanup)
        return

    from whispercrawl.scheduler import start_scheduler
    start_scheduler(config)


if __name__ == "__main__":
    main()
