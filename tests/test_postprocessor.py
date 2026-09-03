"""Post-processing in the consolidated-result pipeline (EPIC-047).

The `_fix` sidecar and `postprocessing.replace_transcription` were retired: the
single per-file result always shows the best available transcript — the
post-processed text when post-processing ran, else the raw transcript.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from asr_crawler.config import (
    Config,
    DirSummarizationConfig,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    TranscriptionConfig,
)
from asr_crawler.main import run_pipeline


def _config(tmp_path: Path, replace_transcription: bool = False) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(
            llm_enabled=True,
            regex_enabled=False,
            output_suffix="_fix",
            replace_transcription=replace_transcription,
        ),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


TRANSCRIPT = "raw transcript"
FIXED = "fixed transcript"


def _make_transcriber(response=TRANSCRIPT):
    inst = MagicMock()
    inst.transcribe.return_value = response
    return MagicMock(return_value=inst)


def _make_postprocessor(response=FIXED):
    inst = MagicMock()
    inst.process.return_value = response
    return MagicMock(return_value=inst)


def _make_postprocessor_failing(exc):
    from asr_crawler.pipeline.postprocessor import PostProcessingError
    inst = MagicMock()
    inst.process.side_effect = PostProcessingError(exc)
    return MagicMock(return_value=inst)


def _svc_logger_patch():
    svc_log = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=svc_log)
    ctx.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=ctx)


def _run(cfg, transcriber_cls, postprocessor_cls):
    with (
        patch("asr_crawler.pipeline.transcriber.Transcriber", transcriber_cls),
        patch("asr_crawler.pipeline.postprocessor.PostProcessor", postprocessor_cls),
        patch("asr_crawler.utils.service_logger.ServiceLogger", _svc_logger_patch()),
    ):
        run_pipeline(cfg)


class TestConsolidatedResult:
    def test_result_holds_postprocessed_text(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), _make_transcriber(), _make_postprocessor())

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == FIXED
        assert not (tmp_path / "a_fix.txt").exists()

    def test_postprocess_failure_records_error_and_no_result(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), _make_transcriber(), _make_postprocessor_failing("boom"))

        assert not (tmp_path / "a_fix.txt").exists()
        assert not (tmp_path / "a_err.txt").exists()  # no sidecar (EPIC-049)
        assert not (tmp_path / "a.txt").exists()  # a failed step → no consolidated result

        from asr_crawler.state import ProcessingState

        with ProcessingState.open(tmp_path / "db" / "state.db") as st:
            errs = st.get_errors("a.mp3")
        assert [e.step for e in errs] == ["postprocess"]
        assert "boom" in errs[0].message


class TestReplaceTranscriptionDeprecated:
    def test_replace_transcription_true_is_a_noop(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path, replace_transcription=True), _make_transcriber(), _make_postprocessor())

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == FIXED
        assert not (tmp_path / "a_fix.txt").exists()

    def test_config_warns_on_deprecated_field(self, tmp_path, caplog):
        import logging as _logging

        p = tmp_path / "config.yaml"
        p.write_text(
            f"watch_dir: {tmp_path}\nextensions: [.mp3]\n"
            "postprocessing:\n  replace_transcription: true\n",
            encoding="utf-8",
        )
        from asr_crawler.config import load_config

        with caplog.at_level(_logging.WARNING):
            load_config(p)
        assert "replace_transcription is deprecated" in caplog.text
