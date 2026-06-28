# whispercrawl

Batch audio/video transcription pipeline powered by [whisper-asr-webservice](https://github.com/ahmetoner/whisper-asr-webservice) and [Ollama](https://ollama.com).

```text
audio/video file
  → Transcription (whisper)   → <file>.txt
  → Post-processing (ollama)  → <file>_fix.txt
  → Per-file summary (ollama) → <file>_sum.txt
  → Formatter                 → converts .txt outputs to .md or .html

after all files in a directory:
  → Directory summary (ollama) → <dirname>_sum.txt
  → Formatter                  → converts directory summary
```

Output extension depends on `formatter.format` (`txt` / `md` / `html`).

---

## Requirements

- Python 3.11+
- Docker (for dev services) **or** external whisper-asr-webservice + Ollama
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/ka1ita/whispercrawl.git
cd whispercrawl
pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv sync
```

### 2. Start dev services

```bash
mkdir -p audio logs
docker compose -f deploy/dev/docker-compose.dev.yml up -d
```

This starts whisper-asr-webservice, Ollama, and whispercrawl in Docker. Pull the LLM model before first use:

```bash
docker compose -f deploy/dev/docker-compose.dev.yml exec ollama ollama pull gemma3:1b
```

**Speaker diarization** requires a HuggingFace token (whisperx uses pyannote.audio):

1. Accept the model licence at <https://huggingface.co/pyannote/speaker-diarization-3.1>
2. Create a token at <https://huggingface.co/settings/tokens>
3. Add it to `deploy/dev/.env` (copy from `deploy/dev/.env.example`):

   ```env
   HF_TOKEN=hf_your_token_here
   ```

To apply config changes to already-running containers:

```bash
# Recreate only the whisper container (picks up new HF_TOKEN from .env)
docker compose -f deploy/dev/docker-compose.dev.yml up -d --force-recreate whisper

# Verify the token is visible inside the container
docker compose -f deploy/dev/docker-compose.dev.yml exec whisper env | grep HF_TOKEN
```

### 3. Configure

Edit [config.yaml](config.yaml) — at minimum set `watch_dir` to your audio directory:

```yaml
watch_dir: ./audio/

transcription:
  language: en           # or "auto" for auto-detect
  model: base            # tiny | base | small | medium | large

postprocessing:
  llm_enabled: true
  model: gemma3:1b

file_summarization:
  llm_enabled: true
  summarize_source: postprocessed   # "postprocessed" | "original"
  model: gemma3:1b
```

### 4. Run

```bash
# Process all files once and exit
python -m whispercrawl --config config.yaml --once

# Dry-run: list files that would be processed, no API calls
python -m whispercrawl --config config.yaml --once --dry-run

# Run on a schedule (uses schedule.interval / schedule.cron from config)
python -m whispercrawl --config config.yaml

# Delete all generated output files
python -m whispercrawl --config config.yaml --once --cleanup
```

If `whispercrawl` is on your PATH after `pip install -e .`:

```bash
whispercrawl --config config.yaml --once
```

---

## Configuration reference

| Section | Key | Default | Description |
| --- | --- | --- | --- |
| *(root)* | `watch_dir` | — | Directory to scan recursively |
| | `extensions` | — | File extensions to process (e.g. `.mp3`, `.wav`) |
| | `rescan` | `false` | `true` = reprocess files that already have output in any format (`.txt`, `.md`, or `.html`) |
| `transcription` | `url` | `http://localhost:9000` | whisper-asr-webservice base URL |
| | `language` | `auto` | Language code or `auto` |
| | `diarize` | `false` | Enable speaker diarization |
| | `timeout` | `300` | HTTP timeout in seconds |
| `postprocessing` | `llm_enabled` | `true` | Run LLM correction via Ollama |
| | `regex_enabled` | `true` | Run regex cleanup pass |
| | `regex_patterns` | `[]` | List of regex patterns to strip |
| | `model` | `llama3.2` | Ollama model name |
| | `prompt` | — | System prompt for the LLM |
| `file_summarization` | `llm_enabled` | `true` | Generate per-file summary |
| | `summarize_source` | `postprocessed` | Input: `postprocessed` (`_fix.txt`) or `original` (`.txt`) |
| `dir_summarization` | `llm_enabled` | `true` | Generate per-directory summary from per-file summaries |
| `schedule` | `interval` | — | e.g. `30m`, `1h`, `600s` |
| | `cron` | — | Standard cron expression, e.g. `"0 * * * *"` |
| `formatter` | `format` | `txt` | Output format: `txt` \| `html` \| `md` |
| | `enabled` | `true` | `false` = skip format conversion; files stay as `.txt` |
| | `speaker_style` | `bold` | Speaker label emphasis (html/md only): `bold` \| `italic` \| `plain` |
| | `text_placement` | `same_line` | Transcript placement after speaker label: `same_line` \| `new_line` |
| `cleanup` | `targets` | `"" _fix _sum _diarize.json` | Output label suffixes to remove on cleanup |
| | `on` | `success` | `success` = only clean after full success; `always` = clean regardless |
| `logging` | `app_log_file` | *(console only)* | Path to rotating application log file |
| | `app_log_level` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| | `requests` | `false` | Write structured ndjson log of all HTTP calls |
| | `log_dir` | — | Directory for `service_requests.ndjson` |
| | `max_text_length` | *(unlimited)* | Truncate request/response text in service log |

### Language detection from filename

Append `_ru`, `_en`, or `_auto` to a filename to override the configured language for that file:

```text
interview_2024_ru.mp3  →  transcribed as Russian
meeting_en.wav         →  transcribed as English
```

---

## Output files

For each audio/video file `<stem>.<ext>` the pipeline writes:

| File | Produced by | When |
| --- | --- | --- |
| `<stem>.<fmt>` | Transcription + Formatter | Always on success |
| `<stem>_fix.<fmt>` | Post-processing + Formatter | When `postprocessing.llm_enabled` or `regex_enabled` |
| `<stem>_sum.<fmt>` | Per-file summary + Formatter | When `file_summarization.llm_enabled` |
| `<dirname>_sum.<fmt>` | Directory summary + Formatter | When `dir_summarization.llm_enabled`, after all files in dir |
| `<stem>_err.txt` | Any step | On error — always `.txt` regardless of format |

`<fmt>` is `txt`, `md`, or `html` depending on `formatter.format` (default `txt`).

All pipeline steps write plain `.txt` internally; the Formatter converts to the final format and removes the `.txt` originals.

---

## Development

```bash
# Run tests
pytest

# Lint and format
ruff check src tests
ruff format src tests
```

---

## Docker deployments

Two compose configurations are provided — pick the one that matches your environment.

### Directory layout

```text
Dockerfile                              # whispercrawl image (multi-stage, non-root)
deploy/
  dev/
    .env.example                        # environment variable template (copy to .env here)
    docker-compose.dev.yml              # all three services in Docker
    docker-compose.services.yml         # whisper + ollama only (run whispercrawl locally)
    start.sh / stop.sh / rebuild.sh / start-external.sh
  prod/
    docker-compose.prod.yml             # whispercrawl only — URLs from environment variables
    setup.sh / service-start.sh / service-down.sh
    DEPLOY.md                           # production deployment guide
deploy/dev/build-prod.sh                  # build + export image to deploy/prod/dist/
```

All compose files mount the following into the container:

| Mount | Host path | Purpose |
| --- | --- | --- |
| `/audio` | `./audio/` | Audio/video files to process (`watch_dir: /audio` in config) |
| `/config.yaml` | `./config.yaml` | Pipeline config (read-only) |
| `/logs` | `./logs/` | Application log + service request log |

---

### Dev — all services in Docker

```bash
mkdir -p audio logs
docker compose -f deploy/dev/docker-compose.dev.yml up -d

# pull the LLM model (first time only)
docker compose -f deploy/dev/docker-compose.dev.yml exec ollama ollama pull gemma3:1b

# run once
docker compose -f deploy/dev/docker-compose.dev.yml run --rm whispercrawl --once

# rebuild whispercrawl image after changing src/ or pyproject.toml
docker compose -f deploy/dev/docker-compose.dev.yml up -d --build whispercrawl
```

---

### Production — external whisper + Ollama

Config values written as `${VAR}` are expanded from the container's environment at startup.

```bash
mkdir -p audio logs
cp .env.example .env          # edit: set WHISPER_URL and OLLAMA_URL
cd deploy/prod && bash service-start.sh
```

---

### Air-gap / production installation

On an internet-connected machine (run from the repo root):

```bash
bash deploy/dev/build-prod.sh
# builds whispercrawl:latest, exports to deploy/prod/dist/
# also copies config.yaml into deploy/prod/
```

Transfer `deploy/prod/` to the target host and follow [deploy/prod/DEPLOY.md](deploy/prod/DEPLOY.md).
