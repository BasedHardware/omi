# OMI CLI Quickstart (Қазақша)

Sections:
## Алдын ала талаптар (Prerequisites)
- Python 3.10+
- pip
- Bluetooth? OMI wearable maybe need Bluetooth? But user only says Python 3.10+, pip. Could mention Bluetooth if pairing. But prerequisites maybe include Bluetooth? Since device pairing. But user specified Prerequisites: Python 3.10+, pip. Could include only those, maybe optional Bluetooth. Need not overdo.

## Орнату (Installation)
```bash
pip install omi-cli
```
Check:
```bash
omi --version
```
Maybe virtual env:
```bash
python -m venv .venv
source .venv/bin/activate
pip install omi-cli
```
But commands English. Explanations Kazakh.

## Құрылғыны жұптастыру және авторизация (Pairing & Auth)
```bash
omi setup
```
Explain follow prompts, select device, allow mic, etc. Maybe if auth token:
```bash
omi setup --help
```
But don't invent flags? Could mention if prompted. Need avoid false specifics? Could say "нұсқауларды орындаңыз". Maybe include `omi setup` interactive.

## Негізгі командалар (Core Commands)
Table? Kazakh.
- `omi listen`: real-time transcription and monitoring. Example:
```bash
omi listen
```
Maybe options? Don't invent. Could say `--help`.
- `omi record`: microphone recording.
```bash
omi record
```
- `omi memories`: memory management.
```bash
omi memories
```
Maybe list/add? Don't invent. Could say `omi memories --help`.
- `omi chat`: intelligent conversation.
```bash
omi chat
```
Maybe `omi chat "Сұрағыңыз"`? Is that safe? CLI chat likely accepts prompt? But not specified. Could avoid invented args. Use interactive.

## Жиі кездесетін мәселелер және ақауларды жою (Troubleshooting)
- `omi: command not found`: pip bin path, reinstall, PATH.
- Python version: check `python --version`.
- microphone permission: OS settings.
- Bluetooth pairing: device on, close, restart `omi setup`.
- network/auth: check internet, re-run setup.
- logs/help: `omi --help`, `omi <command> --help`.
Need Kazakh.

Need ensure all text Kazakh. Some English terms in parentheses okay? User says all explanatory text in Kazakh, commands/code English. Could include English section names? They requested structure includes English names? It says structure contains: title, prerequisites (Prerequisites...), etc. Could use bilingual headings? Maybe headings in Kazakh with English in parentheses? They said all explanatory text Kazakh, commands English. Headings can be Kazakh. But structure includes English labels maybe okay. To be safe, headings Kazakh with English in parentheses? That includes English explanatory? Maybe not. But user specifically lists English terms. Could use Kazakh headings only. But maybe include English in parentheses for clarity. They asked "原汁原味 Kazakh language exclusive". Better headings in Kazakh, maybe English terms in parentheses are not explanatory? Could be okay. But "全部使用地道的 Қазақша 撰写说明文字" means explanatory text Kazakh. Headings are explanatory. Use Kazakh headings. Could include English command names in code.

Need maybe use "Қазақша" in title exactly: # OMI CLI Quickstart (Қазақша). Good.

Need ensure no preface. Final starts with #.

Let's craft polished Kazakh. Need be native-like. Use terms:
- Алдын ала талаптар
- Орнату
- Құрылғыны жұптастыру және авторизация
- Негізгі командалар
- Жиі кездесетін мәселелер және ақауларды жою

Kazakh text:
"OMI CLI — BasedHardware/omi жобасының бұлтты/жергілікті құралдарымен жұмыс істейтін командалық жол интерфейсі." But maybe no need.

Prereq:
"Python 3.10 немесе одан жоғары нұсқа орнатылған болуы керек."
"pip пакет менеджері қолжетімді болуы керек."
"OMI құрылғысы қосулы және Bluetooth арқылы байланысуға дайын болуы мүмкін." Is that extra? Could include as optional. But prerequisites specified only Python/pip. Maybe mention "Жұптастыру үшін Bluetooth қолдауы қажет болуы мүмкін". That's explanatory Kazakh.

Installation:
"Терминалды ашып, мына команданы орындаңыз:"
```bash
pip install omi-cli
```
"Орнату сәтті өткенін тексеру:"
```bash
omi --version
```
"Егер жүйелік Python ортасына өзгеріс енгізгіңіз келмесе, виртуалды орта қолданыңыз:"
```bash
python -m venv .venv
source .venv/bin/activate
pip install omi-cli
```
For Windows: `source` not work. Could include:
```bash
.venv\Scripts\activate
```
But code English. Good.

Pairing:
"Бірінші рет қолданғанда құрылғыны жұптастыру және кіру деректерін реттеу үшін:"
```bash
omi setup
```
"Команда интерактивті режимде сұрақтар қояды. Қажетті нұсқауларды орындаңыз: құрылғыны таңдау, микрофонға рұқсат беру, қажет болса аккаунт/токен арқылы авторизациядан өту."
"Реттеу аяқталған соң:"
```bash
omi --help
```

Core commands:
Maybe table:
| Команда | Мақсаты | Мысал |
But table text Kazakh. Code in examples.
Need maybe not too much invented. Use `--help` for options.

`omi listen`:
"Нақты уақыт режимінде тыңдау, транскрипция және мониторинг."
```bash
omi listen
```
"Тоқтау үшін әдетте Ctrl+C қолданылады." Is Ctrl+C English? It's key. Fine.

`omi record`:
"Микрофоннан жазба алу."
```bash
omi record
```
"Жазба аяқталғаннан кейін файлдың сақталған жерін тексеріңіз." But don't know path. Could say "команда шығаратын жолды назар аударыңыз".

`omi memories`:
"Жадтарды қарау, басқару немесе тазалау."
```bash
omi memories
```
"Қолжетімді ішкі командаларды көру:"
```bash
omi memories --help
```

`omi chat`:
"OMI-мен сұхбаттасу, сұрақ қою немесе контекст бойынша жауап алу."
```bash
omi chat
```
"Интерактивті режимде сұрақ жазыңыз."

Troubleshooting:
Use bullet list.
- `omi: command not found` / `omi: команда табылмады`: "pip орнатқан жол PATH-та жоқ болуы мүмкін. Python ортасын қайта іске қосыңыз немесе PATH-ты жаңартыңыз. Виртуалды орта қолдансаңыз, оны белсендіріңіз."
- "Python нұсқасы сәйкес келмейді": `python --version`.
- "Микрофон жұмыс істемейді": OS permissions.
- "Bluetooth арқылы жұптастыру сәтсіз": device on, close, restart setup.
- "Авторизация қатесі": re-run setup, check network.
- "Көмек алу": `omi --help`, `omi <command> --help`.

Need maybe include "Қауіпсіздік ескертуі"? Not required. Could include note: "Жеке деректерді қорғау үшін `omi memories` арқылы жазбаларды уақытында шолып отырыңыз." Nice.

Need ensure Kazakh grammar. Let's refine.

Potential Kazakh terms:
- "командалық жол" = command line.
- "терминал" okay.
- "жұптастыру" pairing.
- "авторизация" maybe "кіру" or "авторизация". Use