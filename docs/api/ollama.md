# Ollama API

Default local URL: `http://localhost:11434`
OpenAI-compatible endpoint: `http://localhost:11434/v1`

## Chat Completion (used for post-processing and summarization)

```
POST /api/chat
Content-Type: application/json

{
  "model": "llama3.2",
  "messages": [
    {"role": "system", "content": "<prompt from config>"},
    {"role": "user", "content": "<transcription text>"}
  ],
  "stream": false
}
```

## Key Notes

- Use `stream: false` to get a single response object
- Model must be pulled before use: `ollama pull <model>`
- Prompts are configured per-stage in `config.yaml` (fix prompt, file summary prompt, dir summary prompt)
