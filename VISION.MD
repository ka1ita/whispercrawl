# Brief description of the project

The Python service should implement a set of audio and video files in a recursive file directory.:

1) Transcription and diarization;
2) Post-processing - error removal via regex, error removal via promt to ollama.
3) Summarization - via promt to ollama.
4) Summarizing all files in the directory.
The service should start on schedule.

## Services used

Whisper-asr-webservice should be used for transcription and diarization.
Ollama should be used for post-processing and summarization.

## Service configuration file

The service should be configured via a configuration file.
Parameters:

1) A directory for work, a list of file extensions.
2) Transcription and diarization settings - whisper-asr-webservice URL, model type, default language (auto, ru, en), output file name postfix (missing - .txt by default), etc.
3) Post-processing settings - URL ollama, LLM, promt, postfix of the output file name (_fix.txt by default), etc.
4) File summarization settings - URL ollama, LLM, promt, postfix of the output file name (_sum.txt by default), etc.
5) Catalog summarization settings - URL ollama, LLM, promt, postfix of the output file name (_sum.txt by default), etc.
6) Crawl type - only unprocessed files (if an audio and video file has been created .txt file, then it is not processed) or a complete re-crawl.
7) Error handling - postfix the output file name (_err.txt by default), etc.

## Conventions

If the file name contains the postfix _ru, _en, _auto, then this is passed to whisper-asr-webservice as the language. If there is no postfix, then the default language is passed from the configuration file.

A .txt file is created only if its processing was completed without errors.

## Work results

Text files should be created next to each audio recording containing:

1) The results of transcription and diarization are file name + .txt by default (configured in the configuration file).
2) Post-processing results - file name + _fix.txt by default (it is configured in the configuration file).
3) The results of the summation are the file name + _sum.txt by default (it is configured in the configuration file).

Each directory should have a summation file with the name of the directory + _sum.txt by default (it is configured in the configuration file).

## The development process

Create a project template based on the best practices of working with Claude - the directory structure of epics, tasks, documentation, architecture, file templates, etc.
For the test environment, there is a Windows 11 computer with docker and ollama.
For a productive environment, there is a server running on RedOS 8 and external whisper services-asr-webservice, ollama.