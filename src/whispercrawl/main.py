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
    ext = ".html" if fmt == "html" else ".txt"
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


def _write_error(file_path: Path, error_suffix: str, fmt: str, message: str) -> None:
    err_path = output_path(file_path, error_suffix, fmt)
    err_path.write_text(message, encoding="utf-8")


def run_cleanup(config: Config, dry_run: bool = False) -> None:
    """Delete pipeline output files under watch_dir without running the pipeline."""
    fmt = config.output_format
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
    for dir_path in sorted(dirs_seen):
        for suffix in targets:
            dir_base = dir_path / dir_path.name
            dir_sum = (
                dir_path / (dir_path.name + suffix)
                if suffix.endswith(".json")
                else output_path(dir_base, suffix, fmt)
            )
            if dir_sum.exists():
                if dry_run:
                    logger.info("Would clean: %s", dir_sum)
                else:
                    dir_sum.unlink()
                    logger.info("Cleaned: %s", dir_sum)
                removed += 1

    # Remove all error files unconditionally (not restricted to cleanup.targets)
    ext = ".html" if fmt == "html" else ".txt"
    err_suffixes = {
        config.transcription.error_suffix,
        config.postprocessing.error_suffix,
        config.file_summarization.error_suffix,
        config.dir_summarization.error_suffix,
    }
    for suffix in sorted(err_suffixes):
        for err_file in sorted(config.watch_dir.rglob(f"*{suffix}{ext}")):
            if dry_run:
                logger.info("Would clean: %s", err_file)
            else:
                err_file.unlink()
                logger.info("Cleaned: %s", err_file)
            removed += 1

    if removed == 0:
        logger.info("No output files found in %s", config.watch_dir)


def run_pipeline(config: Config, dry_run: bool = False, cleanup: bool = False) -> None:
    """Execute the full pipeline for all matching files."""
    from whispercrawl.file_walker import iter_media_files
    from whispercrawl.pipeline.cleaner import Cleaner
    from whispercrawl.pipeline.postprocessor import PostProcessor, PostProcessingError
    from whispercrawl.pipeline.summarizer import Summarizer, SummarizationError
    from whispercrawl.pipeline.transcriber import Transcriber, TranscriptionError
    from whispercrawl.utils.service_logger import ServiceLogger

    files = list(iter_media_files(
        config.watch_dir,
        config.extensions,
        config.transcription.output_suffix,
        config.rescan,
        config.output_format,
    ))

    if dry_run:
        if not files:
            logger.info("No files to process in %s", config.watch_dir)
        for f in files:
            logger.info("Would process: %s", f)
        return

    fmt = config.output_format
    cleaner = Cleaner(config.cleanup, fmt) if cleanup else None

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
        dir_summarizer = (
            Summarizer(config.dir_summarization, svc_log)
            if config.dir_summarization.llm_enabled else None
        )

        dirs_with_files: set[Path] = set()

        for file_path in files:
            logger.info("Processing: %s", file_path)
            success = True

            try:
                transcript = transcriber.transcribe(file_path)
            except TranscriptionError as e:
                logger.error("Transcription failed for %s: %s", file_path, e)
                _write_error(file_path, config.transcription.error_suffix, fmt, str(e))
                if cleaner:
                    cleaner.clean(file_path, success=False)
                continue

            txt_path = output_path(file_path, config.transcription.output_suffix, fmt)
            txt_path.write_text(render_output(transcript, fmt), encoding="utf-8")
            logger.info("Transcript written: %s", txt_path)
            dirs_with_files.add(file_path.parent)

            fixed_text = None

            if postprocessor:
                try:
                    fixed_text = postprocessor.process(transcript)
                    fix_path = output_path(file_path, config.postprocessing.output_suffix, fmt)
                    fix_path.write_text(render_output(fixed_text, fmt), encoding="utf-8")
                    if config.postprocessing.replace_transcription:
                        fix_path.replace(txt_path)
                        logger.info("Replaced transcript with post-processed: %s", txt_path)
                    else:
                        logger.info("Post-processed: %s", fix_path)
                except PostProcessingError as e:
                    logger.error("Post-processing failed for %s: %s", file_path, e)
                    _write_error(file_path, config.postprocessing.error_suffix, fmt, str(e))
                    success = False

            if file_summarizer:
                summary_input = _pick_summary_input(
                    config.file_summarization.summarize_source,
                    transcript,
                    fixed_text,
                    file_path.name,
                )
                try:
                    summary = file_summarizer.summarize_file(summary_input, file=file_path.name)
                    sum_path = output_path(file_path, config.file_summarization.output_suffix, fmt)
                    sum_path.write_text(render_output(summary, fmt), encoding="utf-8")
                    logger.info("File summary written: %s", sum_path)
                except SummarizationError as e:
                    logger.error("File summarization failed for %s: %s", file_path, e)
                    _write_error(file_path, config.file_summarization.error_suffix, fmt, str(e))
                    success = False

            if cleaner:
                cleaner.clean(file_path, success)

            if success:
                err_path = output_path(file_path, config.transcription.error_suffix, fmt)
                if err_path.exists():
                    err_path.unlink()
                    logger.debug("Removed stale error file: %s", err_path)

        if dir_summarizer:
            for dir_path in sorted(dirs_with_files):
                dir_base = dir_path / dir_path.name
                dir_err_path = output_path(dir_base, config.dir_summarization.error_suffix, fmt)
                try:
                    dir_summary = dir_summarizer.summarize_directory(
                        dir_path, config.file_summarization.output_suffix, fmt
                    )
                    dir_sum_path = output_path(dir_base, config.dir_summarization.output_suffix, fmt)
                    dir_sum_path.write_text(render_output(dir_summary, fmt), encoding="utf-8")
                    logger.info("Directory summary written: %s", dir_sum_path)
                    if dir_err_path.exists():
                        dir_err_path.unlink()
                        logger.debug("Removed stale error file: %s", dir_err_path)
                except SummarizationError as e:
                    logger.error("Directory summarization failed for %s: %s", dir_path, e)
                    dir_err_path.write_text(str(e), encoding="utf-8")


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
