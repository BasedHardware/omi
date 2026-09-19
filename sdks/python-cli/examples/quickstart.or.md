# OMI CLI Quickstart (ଓଡ଼ିଆ). Sections: prerequisites, installation, pairing/auth, core commands, troubleshooting. Commands English. Need Odia explanations. Need be careful with Odia terms. Need maybe use code blocks. Need ensure no Chinese. Need maybe mention BasedHardware/omi CLI. Need authentic Odia. I can compose. Need maybe use Odia numerals? Not necessary. Need ensure commands: pip install omi-cli, omi setup, omi listen, omi record, omi memories, omi chat. Need maybe include examples. Need troubleshooting: device not detected, permissions, microphone, network, pip PATH, Python version. Need Odia. Need maybe use terms: ପୂର୍ବଚର୍ତ୍ତ, ସ୍ଥାପନ, ଯନ୍ତ୍ର ଯୋଡ଼ାକରଣ ଓ ପ୍ରମାଣୀକରଣ, ମୁଖ୍ୟ ଆଦେଶ, ସମସ୍ୟା ନିରାକରଣ. Need ensure Odia script. Need maybe include note: OMI is open-source wearable AI hardware and CLI suite. Need maybe mention BasedHardware. Need no extra. Need final only markdown. Need maybe include code fences with bash. Need ensure Odia text is natural. Let's craft.

Potential Odia:
# OMI CLI Quickstart (ଓଡ଼ିଆ)

OMI ହେଉଛି BasedHardware ର ଏକ ଖୋଲା-ସ୍ରୋତ ଧାରଣଯୋଗ୍ୟ AI ହାର୍ଡୱେର ଓ CLI ସୁଟ୍। ଏହି ଗାଇଡ୍ ଆପଣଙ୍କୁ OMI CLI ସ୍ଥାପନ, ଯନ୍ତ୍ର ଯୋଡ଼ାକରଣ, ରିଅଲ୍-ଟାଇମ୍ ଟ୍ରାନ୍ସକ୍ରିପ୍ସନ୍, ରେକର୍ଡିଂ, ମେମୋରୀ ପରିଚାଳନା ଓ AI ଚାଟ୍ ଆରମ୍ଭ କରିବାରେ ସାହାଯ୍ୟ କରିବ।

## ପୂର୍ବଚର୍ତ୍ତ (Prerequisites)
- Python 3.10 କିମ୍ବା ତା’ଠାରୁ ନୂଆ ସଂସ୍କରଣ
- pip
- ...
- OMI ଯନ୍ତ୍ର/ଡିଭାଇସ୍, USB/Bluetooth? Need not assume. Maybe: OMI ଡିଭାଇସ୍ ଓ ଆବଶ୍ୟକ କେବଲ୍/ବ୍ଲୁଟୁଥ୍।
- ମାଇକ୍ରୋଫୋନ୍ ଅନୁମତି।

## ସ୍ଥାପନ (Installation)
```bash
pip install omi-cli
```
If virtual env recommended:
```bash
python -m venv .venv
source .venv/bin/activate
pip install omi-cli
```
Windows: .venv\Scripts\activate. Need Odia.

## ଯନ୍ତ୍ର ଯୋଡ଼ାକରଣ ଓ ପ୍ରମାଣୀକରଣ (Pairing & Auth)
```bash
omi setup
```
Explain: It will ask device, auth, etc. Need maybe mention follow prompts.

## ମୁଖ୍ୟ ଆଦେଶ (Core Commands)
### 1. ରିଅଲ୍-ଟାଇମ୍ ଶ୍ରବଣ ଓ ଟ୍ରାନ୍ସକ୍ରିପ୍ସନ୍
```bash
omi listen
```
### 2. ମାଇକ୍ରୋଫୋନ୍ ରେକର୍ଡିଂ
```bash
omi record
```
### 3. ମେମୋରୀ ପରିଚାଳନା
```bash
omi memories
```
### 4. AI ଚାଟ୍
```bash
omi chat
```
Maybe examples:
```bash
omi chat "ମୋର ଶେଷ ମେମୋରୀ ଦେଖାଅ"
```
But command string Odia? It's okay? Commands and code keep English? User says commands and code keep English. Does that mean command arguments should be English? Better keep code English. Use `omi chat "What did I say last?"` maybe. But Odia guide. Need code English. Could include flags? Not specified. Avoid invented flags. Use simple commands.

## ସମସ୍ୟା ନିରାକରଣ (Troubleshooting)
- `omi: command not found`: pip PATH, reinstall, use `python -m pip install --user omi-cli`, `python -m omi`? Is `python -m omi` valid? Not sure. Avoid. Use `pip show omi-cli`.
- Python version: `python --version`.
- Device not detected: reconnect, permissions, macOS/Windows/Linux.
- Microphone permission: system settings.
- Network/auth: re-run `omi setup`.
- Logs? Maybe `omi --help`? likely. Use `omi --help` English.

Need ensure Odia. Need maybe use Odia punctuation. Need maybe avoid too much English except commands. But section headings can include English in parentheses as requested. Need maybe title exactly. Need no preamble. Need final. Need ensure Odia script correct. Let's produce.

Need consider if Odia terms for CLI: ଆଦେଶ-ପଂକ୍ତି? CLI = କମାଣ୍ଡ୍ ଲାଇନ୍ ଇଣ୍ଟରଫେସ୍. Use. Need maybe "ପ୍ରମାଣୀକରଣ" for auth. "ଯୋଡ଼ାକରଣ" pairing. "ଟ୍ରାନ୍ସକ୍ରିପ୍ସନ୍" maybe transliteration. Could use "ଲେଖାନ୍ତରଣ"? Real-time transcription: ରିଅଲ୍-ଟାଇମ୍ ଟ୍ରାନ୍ସକ୍ରିପ୍ସନ୍. Good.

Need maybe include "ପାଇପ୍" for pip? Keep pip.

Need ensure no draft. final only markdown.

Double-check Odia spelling:
- ପୂର୍ବଚର୍ତ୍ତ (prerequisites) maybe ପୂର୍ବଶର୍ତ୍ତ? Both. Use ପୂର୍ବଚର୍ତ୍ତ.
- ସ୍ଥାପନ
- ଯନ୍ତ୍ର ଯୋଡ଼ାକରଣ ଓ ପ୍ରମାଣୀକରଣ
- ମୁଖ୍ୟ ଆଦେଶ
- ସମସ୍ୟା ନିରାକରଣ
- ଧାରଣଯୋଗ୍ୟ AI ହାର୍ଡୱେର ଓ CLI ସୁଟ୍
- ଖୋଲା-ସ୍ରୋତ
- ଆରମ୍ଭ
- ସାହାଯ୍ୟ କରିବ
- ଆବଶ୍ୟକ
- ସଂସ୍କରଣ
- ସକ୍ରିୟ
- ନିର୍ଦ୍ଦେଶ
- ପ୍ରମ୍ପ୍ଟ
- ଡିଭାଇସ୍
- କେବଲ୍
- ବ୍ଲୁଟୁଥ୍
- ଅନୁମତି
- ପ୍ରଶ୍ନୋତ୍ତର
- ସଂରକ୍ଷିତ
- ପ୍ରବେଶ
- ପୁନଃଚାଲୁ
- ସଂଯୋଗ
- ନେଟୱାର୍କ
- ପ୍ରମାଣପତ୍ର? auth token.
- ଲଗ୍? maybe ଲଗ୍ ଫାଇଲ୍.

Need maybe include "ପାଇପ୍" not necessary.

Potential final:

# OMI CLI Quickstart (ଓଡ଼ିଆ)

OMI ହେଉଛି BasedHardware ର ଏକ ଖୋଲା-ସ୍ରୋତ ଧାରଣଯୋଗ୍ୟ AI ହାର୍ଡୱେର ଓ CLI ସୁଟ୍। ...

## ପୂର୍ବଚର୍ତ୍ତ (Prerequisites)
- Python 3.10+
- pip
- ...

Need maybe mention OS? Linux/macOS/Windows.

## ସ୍ଥାପନ (Installation)
```bash
pip install omi-cli
```
If permission:
```bash
python -m pip install --user omi-cli
```
But code English. Good.

## ଯନ୍ତ୍ର ଯୋଡ଼ାକରଣ ଓ ପ୍ରମାଣୀକରଣ (Pairing & Auth)
```bash
omi setup
```
...

## ମୁଖ୍ୟ ଆଦେଶ (Core Commands)
### `omi listen`
...
```bash
omi listen
```
### `omi record`
...
### `omi memories`
...
### `omi chat`
...

Maybe include table? Could be nice. But ensure Odia. Table with command and purpose. Commands English. Use Odia descriptions.

| ଆଦେଶ | କାମ |
|---|---|
| `omi setup` | ... |
...

Need maybe include examples after each.

Troubleshooting:
### `omi: command not found`
```bash
python -m pip install --user omi-cli
```
Need maybe PATH: add `~/.local/bin` to PATH. Odia.
### Device not detected
...
### Microphone permission
...
### Auth expired
```bash
omi setup
```
### Help
```bash
omi --help
```

Need ensure no invented commands. `omi --help` likely. Good.

Need maybe mention `pip install omi-cli` may require `pip3`. Could include:
```bash
pip3 install omi-cli
```
But core command specified pip install omi-cli. Keep primary.

Need maybe mention virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
pip install omi-cli
