"""Tests for --cleanup CLI action (run_cleanup) — current-version outputs only (EPIC-052)."""
from pathlib import Path

from asr_crawler.config import (
    Config,
    DirSummarizationConfig,
    FormatterConfig,
    LoggingConfig,
    TranscriptionConfig,
)
from asr_crawler.main import run_cleanup

EXTENSIONS = [".mp3", ".ogg", ".wav"]


def _config(watch_dir: Path, fmt: str = "txt", engine_names=None) -> Config:
    tr = TranscriptionConfig(output_suffix="")
    if engine_names:
        tr.engines = [TranscriptionConfig(name=n) for n in engine_names]
    return Config(
        watch_dir=watch_dir,
        extensions=EXTENSIONS,
        formatter=FormatterConfig(format=fmt),
        transcription=tr,
        dir_summarization=DirSummarizationConfig(underscore_prefix=True),
        logging=LoggingConfig(),
    )


def _touch(path: Path, text: str = "x") -> Path:
    path.write_text(text)
    return path


class TestRemovesConsolidatedResults:
    def test_removes_per_file_result(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        result = _touch(tmp_path / "call.txt")

        run_cleanup(_config(tmp_path))

        assert not result.exists()
        assert audio.exists()

    def test_removes_per_directory_result(self, tmp_path):
        (tmp_path / "rec.ogg").touch()
        dir_result = _touch(tmp_path / ("_" + tmp_path.name + ".txt"))

        run_cleanup(_config(tmp_path))

        assert not dir_result.exists()

    def test_removes_result_in_any_formatter_extension(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        txt = _touch(tmp_path / "call.txt")
        md = _touch(tmp_path / "call.md")
        html = _touch(tmp_path / "call.html")

        run_cleanup(_config(tmp_path, fmt="md"))

        assert not txt.exists()
        assert not md.exists()
        assert not html.exists()

    def test_removes_every_engine_result(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        a = _touch(tmp_path / "call_whisperx.txt")
        b = _touch(tmp_path / "call_faster.txt")
        dir_a = _touch(tmp_path / ("_" + tmp_path.name + "_whisperx.txt"))

        run_cleanup(_config(tmp_path, engine_names=["whisperx", "faster"]))

        assert not a.exists()
        assert not b.exists()
        assert not dir_a.exists()

    def test_recursive_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "meeting.mp3").touch()
        result = _touch(sub / "meeting.txt")

        run_cleanup(_config(tmp_path))

        assert not result.exists()


class TestLeavesLegacyAndSidecarsAlone:
    def test_pre047_sidecars_untouched(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        result = _touch(tmp_path / "call.txt")
        fix = _touch(tmp_path / "call_fix.txt")
        summ = _touch(tmp_path / "call_sum.txt")
        concat = _touch(tmp_path / (tmp_path.name + "_concat.txt"))

        run_cleanup(_config(tmp_path))

        assert not result.exists()
        assert fix.exists()
        assert summ.exists()
        assert concat.exists()

    def test_err_files_untouched(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        err = _touch(tmp_path / "call_err.txt")
        orphan = _touch(tmp_path / "orphan_err.txt")

        run_cleanup(_config(tmp_path))

        assert err.exists()
        assert orphan.exists()

    def test_diarize_json_untouched(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        diarize = _touch(tmp_path / "call_diarize.json")

        run_cleanup(_config(tmp_path))

        assert diarize.exists()


class TestClearsIndex:
    def test_empties_the_processing_index(self, tmp_path):
        from asr_crawler.state import ProcessingState

        (tmp_path / "call.mp3").touch()
        db = tmp_path / "db" / "state.db"
        with ProcessingState.open(db) as st:
            st.mark("call.mp3", "done", 1.0, 1)
            st.record_error("call.mp3", "transcribe", "boom")

        run_cleanup(_config(tmp_path))

        with ProcessingState.open(db) as st:
            assert st.get_errors() == []
            assert st.lookup("call.mp3") is None


class TestDryRun:
    def test_dry_run_keeps_everything(self, tmp_path):
        from asr_crawler.state import ProcessingState

        (tmp_path / "call.mp3").touch()
        result = _touch(tmp_path / "call.txt")
        db = tmp_path / "db" / "state.db"
        with ProcessingState.open(db) as st:
            st.mark("call.mp3", "done", 1.0, 1)

        run_cleanup(_config(tmp_path), dry_run=True)

        assert result.exists()
        with ProcessingState.open(db) as st:
            assert st.lookup("call.mp3") is not None


class TestNoOutputs:
    def test_no_outputs_exits_cleanly(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        run_cleanup(_config(tmp_path))

    def test_empty_dir_exits_cleanly(self, tmp_path):
        run_cleanup(_config(tmp_path))
