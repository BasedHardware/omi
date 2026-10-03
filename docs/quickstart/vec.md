# Venetian (`vec`) AI Agent Quickstart Guide

This guide walks you through running an OMI AI agent with the **Venetian** (`vec`) locale, including text-to-speech, speech-to-text, and prompt handling with Venetian orthography.

## Overview

Venetian (`vec`) is a Romance language spoken in the Veneto region of Italy. It uses the Latin script with a small set of diacritics. OMI's Python CLI supports `vec` as a first-class locale for both transcription and synthesis.

| Property | Value |
| --- | --- |
| ISO 639-1 | `vec` |
| ISO 639-3 | `vec` |
| Script | Latin |
| Default region | `IT` (Italy) |
| BCP-47 tag | `vec-IT` |

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

Set the agent locale to Venetian before starting a session:

```bash
export OMI_LOCALE="vec-IT"
export OMI_LANGUAGE="vec"
```

Or in Python:

```python
from omi import Agent, Locale

agent = Agent(locale=Locale("vec", region="IT"))
```

## Speech-to-text (STT)

```python
from omi import Agent

agent = Agent(locale="vec-IT")
transcript = agent.transcribe("audio/venetian_sample.wav")
print(transcript.text)
# -> "Ciao, come stàtu? Vien qua che te conto na roba."
```

## Text-to-speech (TTS)

```python
agent.speak("Bondì, benvegnùo inte OMI.", voice="vec_female_01")
```

## Prompt handling with Venetian orthography

Venetian uses the grave accent (`à è ì ò ù`) and the diaeresis in some orthographies. Always normalize input to NFC before sending it to the model:

```python
import unicodedata

def normalize_vec(text: str) -> str:
    return unicodedata.normalize("NFC", text)

prompt = normalize_vec("Bondì, come stàtu?")
response = agent.chat(prompt)
print(response)
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Unsupported locale: vec` | Older CLI build | Upgrade: `pip install -U omi-cli` |
| Garbled diacritics | Input not NFC-normalized | Run `unicodedata.normalize("NFC", text)` |
| TTS reads letter-by-letter | Wrong voice pack | Select a `vec_*` voice explicitly |
| STT returns Italian | Fallback locale in use | Set `OMI_LOCALE=vec-IT` before the session |

## See also

- [OMI Python CLI docs](https://docs.omi.me/)
- [Supported locales](https://github.com/BasedHardware/omi#locales)
