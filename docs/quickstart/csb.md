# Kashubian (`csb`) AI Agent Quickstart Guide

This guide walks you through running an OMI AI agent with the **Kashubian** (`csb`) locale, including text-to-speech, speech-to-text, and prompt handling with Kashubian orthography.

## Overview

Kashubian (`csb`) is a West Slavic language (Lechitic group) spoken in the Pomerania region of northern Poland. It uses the Latin script with extended diacritics including `ã`, `ë`, `ò`, `ô`, and `ù`. OMI's Python CLI supports `csb` as a first-class locale for both transcription and synthesis.

| Property | Value |
| --- | --- |
| ISO 639-1 | — (no two-letter code) |
| ISO 639-3 | `csb` |
| Script | Latin |
| Default region | `PL` (Poland) |
| BCP-47 tag | `csb-PL` |

Because Kashubian has no ISO 639-1 code, always use the three-letter code `csb` in `OMI_LANGUAGE` and the full BCP-47 tag `csb-PL` for locale resolution.

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
export OMI_LOCALE="csb-PL"
export OMI_LANGUAGE="csb"
```

Or in Python:

```python
from omi import Agent, Locale

agent = Agent(locale=Locale("csb", region="PL"))
```

## Speech-to-text (STT)

```python
from omi import Agent

agent = Agent(locale="csb-PL")
transcript = agent.transcribe("audio/kaszubski_sample.wav")
print(transcript.text)
# -> "Witôj, jak sã môsz? Przëdzesz tu, to ce cos pòwiém."
```

## Text-to-speech (TTS)

```python
agent.speak("Witôj, witôj w OMI.", voice="csb_female_01")
```

## Prompt handling with Kashubian orthography

Kashubian orthography uses several extended Latin characters, including `ã`, `ë`, `ò`, `ô`, and `ù`. Always normalize input to NFC before sending it to the model:

```python
import unicodedata

def normalize_csb(text: str) -> str:
    return unicodedata.normalize("NFC", text)

prompt = normalize_csb("Witôj, jak sã môsz?")
response = agent.chat(prompt)
print(response)
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Unsupported locale: csb` | Older CLI build | Upgrade: `pip install -U omi-cli` |
| Extended glyphs render as `?` | Non-UTF-8 terminal | Set `PYTHONIOENCODING=utf-8` |
| Garbled diacritics | Input not NFC-normalized | Run `unicodedata.normalize("NFC", text)` |
| TTS reads letter-by-letter | Wrong voice pack | Select a `csb_*` voice explicitly |
| STT returns Polish | Fallback locale in use | Set `OMI_LOCALE=csb-PL` before the session |

## See also

- [OMI Python CLI docs](https://docs.omi.me/)
- [Supported locales](https://github.com/BasedHardware/omi#locales)
