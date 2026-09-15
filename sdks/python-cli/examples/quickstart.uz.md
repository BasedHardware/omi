# OMI CLI Quickstart (O'zbekcha). Need prerequisites, installation, pairing/auth, core commands, troubleshooting. Commands English. Need high quality. Need maybe use Uzbek terms: old shartlar, o'rnatish, qurilma juftlash va autentifikatsiya, asosiy buyruqlar, muammolar va xatoliklarni bartaraf etish. Need ensure apostrophe in O'zbekcha maybe use O‘zbekcha? User says O'zbekcha. Use ASCII apostrophe? Could use O'zbekcha. Need maybe mention Python 3.10+, pip. Need commands: pip install omi-cli, omi setup, omi listen, omi record, omi memories, omi chat. Need examples. Need maybe virtualenv. Need troubleshooting: command not found, microphone permissions, Bluetooth pairing, pip PATH, Python version, network. Need Uzbek. Need no extra. Ensure Markdown. Need maybe code fences. Need maybe note: buyruqlar terminalda bajariladi. Need maybe use "O'zbekcha" in title. Need maybe include "Prerequisites" English? Requirement says structure includes prerequisites (Prerequisites: Python 3.10+, pip). Could headings bilingual? Maybe headings in Uzbek with English in parentheses? It says all explanatory text Uzbek, commands and code English. Could headings: "## Old shartlar (Prerequisites)". That's okay. Need maybe "O'zbekcha" apostrophe. Need avoid Chinese. Need final only.

Need think if BasedHardware/omi CLI actual commands? User provided. Need maybe include `omi --version`. Need maybe `omi setup` interactive. Need maybe `omi listen` real-time transcription and monitoring. Need maybe `omi record` microphone recording. Need maybe `omi memories` memory management. Need maybe `omi chat` intelligent conversation. Need maybe examples with flags? We don't know flags. Avoid inventing too much? Could say `omi listen` and `omi record` may ask permissions. Could include `omi memories --help`? But if not known? It's safe? Maybe not. Use only provided commands. Could include `omi chat "savol"`. Need maybe `omi memories` list? Could be interactive. Use `omi memories` to open/manage. Need maybe `omi chat` interactive. Need maybe `omi setup` pairs device and auth. Need maybe `omi listen` starts real-time transcription. Need maybe `omi record` records microphone. Need maybe `omi memories` manage memories. Need maybe `omi chat` chat.

Need ensure Uzbek grammar. Let's draft:

# OMI CLI Quickstart (O'zbekcha)

OMI CLI — BasedHardware/omi loyihasining terminal orqali boshqariladigan buyruq satr vositasi. Ushbu qo'llanma orqali OMI qurilmasini o'rnatish, juftlash va asosiy funksiyalardan foydalanishni tezda o'rganasiz.

## Old shartlar (Prerequisites)

- Python 3.10 yoki undan yangi versiya.
- `pip` paket menejeri o'rnatilgan va terminalda ishlaydi.
- Internet aloqasi (o'rnatish va autentifikatsiya uchun).
- Mikrofon va Bluetooth qurilmasi (real vaqtli transkripsiya, yozib olish va juftlash uchun).
- Terminal yoki PowerShell (Windows), Terminal (macOS/Linux).

Python version check:
```bash
python --version
pip --version
```
If Python 3.10+ not found, install from python.org.

Need Uzbek: "Agar Python 3.10+ ko'rinmasa...".

## O'rnatish (Installation)

Recommended virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```
Windows PowerShell:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
Then install:
```bash
pip install omi-cli
```
Check:
```bash
omi --version
```
If command not found, ensure pip bin path in PATH.

Need maybe `pip install --upgrade omi-cli`.

## Qurilma juftlash va autentifikatsiya (Pairing & Auth)

Run:
```bash
omi setup
```
This command guides: account login/auth, Bluetooth device discovery, pairing, microphone permission, default settings. Keep OMI device near computer, Bluetooth on. If prompted, approve. After success, device connected.

Need maybe `omi setup` may open browser. Use Uzbek.

## Asosiy buyruqlar (Core Commands)

### Real vaqtli transkripsiya va tinglash
```bash
omi listen
```
Starts listening, transcribes speech in real time. Stop Ctrl+C.

### Mikrofon yozuvi
```bash
omi record
```
Records from default microphone. Follow prompts. Output maybe saved? Don't invent path. Could say "buyruq ko'rsatmalariga qarab fayl saqlanadi".

### Xotira boshqaruvi
```bash
omi memories
```
Open memory manager: view, search, edit, delete? If not sure. Could say "xotiralarni ko'rish, qidirish va boshqarish".

### Aqlli suhbat
```bash
omi chat
```
Interactive chat. Or:
```bash
omi chat "Bugun qanday reja?"
```
Need Uzbek example.

Maybe table:
| Buyruq | Vazifa |
|---|---|
| `omi setup` | ... |
...

## Muammolar va xatoliklarni bartaraf etish (Troubleshooting)

### `omi: command not found`
- pip installation path not in PATH.
- Reinstall in active venv.
- Windows: restart terminal.
- Try `python -m pip install omi-cli` and `python -m omi`? Is `python -m omi` valid? Not sure. Avoid. Could say `pip show omi-cli`.

### Python versiyasi eski
Check `python --version`, install 3.10+.

### Bluetooth qurilma topilmayapti
- device charged, Bluetooth on, not connected to phone, close, restart.

### Mikrofon ishlamayapti
- OS permissions, default input device, no other app using mic.

### Transkripsiya kechikayotgan yoki uzilayotgan
- internet, CPU, close heavy apps, move closer.

### Auth error
- rerun `omi setup`, check account, network, time.

### Upgrade
```bash
pip install --upgrade omi-cli
```

Need maybe include "Yordam" `omi --help`? Could include. But commands English. `omi --help` likely works. Could include.

Need ensure no Chinese. Need maybe use Uzbek Latin with apostrophes: o'z, g'oz? Use ASCII apostrophe. Need maybe "O'zbekcha" title. Need maybe "O‘zbekcha"? User uses O'zbekcha. Use O'zbekcha.

Need maybe mention BasedHardware/omi. Need maybe "O'zbekcha" in title exactly. Need final only Markdown.

Need consider if "omi listen" real-time transcription and monitoring. Use "tinglash". Need maybe "real vaqtli transkripsiya". Good.

Need maybe include "Buyruqlar terminalda bajariladi". Good.

Need maybe include "Eslatma: buyruq bayroqlari versiyaga qarab o'zgarishi mumkin; `omi --help` tekshiring." Good.

Need maybe ensure all explanatory text Uzbek. Headings can include English parentheses? Requirement says structure includes English names. It's okay. But "全部使用地道的 O'zbekcha 撰写说明文字，命令与代码保持英文." Headings are explanatory? Could be Uzbek with English in parentheses. Fine.

Need maybe avoid too much English. Code blocks English. Table headings Uzbek.

Need maybe use "pip" in code. Good.

Potential issue: `omi chat "Bugun qanday reja?"` includes Uzbek inside code? It's command argument, maybe okay? Commands and code keep English? It says commands and code keep English. But example argument in Uzbek might violate? Could use English argument: `omi chat "What is my plan today?"` But explanatory text Uzbek. To be safe, code examples English. Use `omi chat "hello"`. But user wants Uzbek guide, not necessarily code English. "命令与代码保持英文" means commands and code English. So examples should be English strings. Use `omi chat "hello"`.

Need maybe `omi record` no args. Good.

Need maybe `omi memories` no args.

Need maybe `omi listen` no args.

Need maybe `omi setup` no args.

Need maybe `pip install omi-cli`.

Need maybe `python -m venv .venv` code English.

Need maybe Windows activation code English.

Need maybe troubleshooting commands English.

Need maybe final no analysis. Ensure starts with `# `.

Let's craft polished Uzbek. Need be native-like. Use terms:
- "Old shartlar" maybe "Talab qilinadigan shartlar".
- "O'rnatish"
- "Qurilma juftlash va autentifikatsiya"
- "Asosiy buyruqlar"
- "Muammolar va xatoliklarni bartaraf etish"

Need maybe "Quickstart" in title English. Good.

Need maybe "OMI CLI — BasedHardware/omi loyihasining buyruq satr vositasi." Good.

Need maybe "Ushbu qo'llanma". Good.

Need maybe "Python 3.10+".