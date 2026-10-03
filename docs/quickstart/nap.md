# Neapolitan (`nap`) AI Agent Quickstart Guide

This guide walks you through running an OMI AI agent with the **Neapolitan** (`nap`) locale, including text-to-speech, speech-to-text, and prompt handling with Neapolitan orthography.

## Overview

Neapolitan (`nap`) is a Romance language spoken in Naples and much of southern Italy. It uses the Latin script with grave and acute accents. OMI's Python CLI supports `nap` as a first-class locale for both transcription and synthesis.

| Property | Value |
| --- | --- |
| ISO 639-1 | `nap` |
| ISO 639-3 | `nap` |
| Script | Latin |
| Default region | `IT` (Italy) |
| BCP-47 tag | `nap-IT` |

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

Set the agent locale to Neapolitan before starting a session:

```bash
export OMI_LOCALE="nap-IT"
export OMI_LANGUAGE="nap"
```

Or in Python:

```python
from omi import Agent, Locale

agent = Agent(locale=Locale("nap", region="IT"))
```

## Speech-to-text (STT)

```python
from omi import Agent

agent = Agent(locale="nap-IT")
transcript = agent.transcribe("audio/napoletano_sample.wav")
print(transcript.text)
# -> "Uè, comme staje? Viene ccà ca te dico na cosa."
```

## Text-to-speech (TTS)

```python
agent.speak("Uè, benvenuto dint' a OMI.", voice="nap_male_01")
```

## Prompt handling with Neapolitan orthography

Neapolitan uses the grave accent (`à è ì ò ù`) and the acute accent (`é ó`) to mark stress. Always normalize input to NFC before sending it to the model:

```python
import unicodedata

def normalize_nap(text: str) -> str:
    return unicodedata.normalize("NFC", text)

prompt = normalize_nap("Uè, comme staje?")
response = agent.chat(prompt)
print(response)
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Unsupported locale: nap` | Older CLI build | Upgrade: `pip install -U omi-cli` |
| Garbled diacritics | Input not NFC-normalized | Run `unicodedata.normalize("NFC", text)` |
| TTS reads letter-by-letter | Wrong voice pack | Select a `nap_*` voice explicitly |
| STT returns Italian | Fallback locale in use | Set `OMI_LOCALE=nap-IT` before the session |

## See also

- [OMI Python CLI docs](https://docs.omi.me/)
- [Supported locales](https://github.com/BasedHardware/omi#locales)
