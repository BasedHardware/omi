# Silesian (`szl`) AI Agent Quickstart Guide

This guide walks you through running an OMI AI agent with the **Silesian** (`szl`) locale, including text-to-speech, speech-to-text, and prompt handling with Silesian orthography.

## Overview

Silesian (`szl`) is a West Slavic language (Lechitic group) spoken in Upper Silesia. It uses the Latin script with a rich set of diacritics, including `ŏ`, `ō`, and `ã`. OMI's Python CLI supports `szl` as a first-class locale for both transcription and synthesis.

| Property | Value |
| --- | --- |
| ISO 639-1 | — (no two-letter code) |
| ISO 639-3 | `szl` |
| Script | Latin |
| Default region | `PL` (Poland) |
| BCP-47 tag | `szl-PL` |

Because Silesian has no ISO 639-1 code, always use the three-letter code `szl` in `OMI_LANGUAGE` and the full BCP-47 tag `szl-PL` for locale resolution.

## Prerequisites

- Python 3.10+
- An OMI API key (`OMI_API_KEY` in your environment)
- `ffmpeg` on your `PATH` (for audio transcoding)

## Install

```bash
pip install omi-cli
# or, from source
git clone https://github.com/BasedHardware/omi.git
cd omi && pip install -e ".[cli]"
```

## Configure the locale

```bash
export OMI_LOCALE="szl-PL"
export OMI_LANGUAGE="szl"
```

Or in Python:

```python
from omi import Agent, Locale

agent = Agent(locale=Locale("szl", region="PL"))
```

## Speech-to-text (STT)

```python
from omi import Agent

agent = Agent(locale="szl-PL")
transcript = agent.transcribe("audio/slaski_sample.wav")
print(transcript.text)
# -> "Witej, jak sie mosz? Przijdziesz sam, to ci cos pedza."
```

## Text-to-speech (TTS)

```python
agent.speak("Witej, witaj w OMI.", voice="szl_female_01")
```

## Prompt handling with Silesian orthography

Silesian orthography uses several extended Latin characters, including `ŏ`, `ō`, `ã`, and `ů`. Always normalize input to NFC before sending it to the model, and be aware that some fonts render the extended glyphs inconsistently:

```python
import unicodedata

def normalize_szl(text: str) -> str:
    return unicodedata.normalize("NFC", text)

prompt = normalize_szl("Witej, jak sie mosz?")
response = agent.chat(prompt)
print(response)
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Unsupported locale: szl` | Older CLI build | Upgrade: `pip install -U omi-cli` |
| Extended glyphs render as `?` | Non-UTF-8 terminal | Set `PYTHONIOENCODING=utf-8` |
| Garbled diacritics | Input not NFC-normalized | Run `unicodedata.normalize("NFC", text)` |
| TTS reads letter-by-letter | Wrong voice pack | Select a `szl_*` voice explicitly |
| STT returns Polish | Fallback locale in use | Set `OMI_LOCALE=szl-PL` before the session |

## See also

- [OMI Python CLI docs](https://docs.omi.me/)
- [Supported locales](https://github.com/BasedHardware/omi#locales)
