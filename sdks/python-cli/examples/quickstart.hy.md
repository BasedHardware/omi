# OMI CLI Quickstart (Հայերեն). Sections: Prerequisites, Installation, Pairing & Auth, Core Commands, Troubleshooting. All explanatory text Armenian, commands/code English. Need maybe use Armenian headings? User says structure includes English labels? Could use Armenian headings with English in parentheses? They specified structure contains: - 标题: # OMI CLI Quickstart (Հայերեն) - 前置要求 (Prerequisites: Python 3.10+, pip) etc. Probably headings can be Armenian with English parenthetical. Need ensure no preface. Need maybe mention pip install omi-cli, omi setup, omi listen, omi record, omi memories, omi chat. Need authentic Armenian. Need be careful with Armenian technical vocabulary. Let's craft.

Need maybe include code blocks with bash. Commands English. Explanations Armenian. Need maybe mention BasedHardware/omi. Need maybe include examples.

Armenian: 
# OMI CLI Quickstart (Հայերեն)

## Նախապես պահանջվող գործիքներ (Prerequisites)
- Python 3.10+
- pip
- ...

Need Armenian: "Նախապես պահանջվող գործիքներ" maybe "Նախապատրաստական պահանջներ". Use "Նախապես պահանջվող միջավայր".

Installation:
```bash
pip install omi-cli
```
If permission: `pip install --user omi-cli` or venv. Armenian: Եթե...

Pairing & Auth:
```bash
omi setup
```
Follow prompts. Maybe `omi setup --help`.

Core Commands:
### Իրական ժամանակում լսում և վերծանում
```bash
omi listen
```
### Խոսափողից ձայնագրում
```bash
omi record
```
### Հիշողությունների կառավարում
```bash
omi memories
```
Examples: `omi memories list`, `omi memories search "..."`? Need not invent? Could include generic. But core commands only. Could show `omi memories --help`.
### Խելացի զրույց
```bash
omi chat
```
Maybe `omi chat "question"`.

Troubleshooting:
- command not found: PATH, pip user bin.
- microphone permission.
- device not pairing: Bluetooth, USB, restart setup.
- Python version.
- logs: `omi --help`, `omi setup --help`.

Need Armenian grammar. Let's ensure natural. Armenian technical terms:
- CLI = հրամանային տողի գործիք? "CLI" can remain.
- install = տեղադրում
- pairing = զույգում / կապակցում. "Սարքի զույգում և հավատարմագրում".
- authentication = հավատարմագրում.
- real-time transcription = իրական ժամանակում վերծանում.
- listening = լսում.
- microphone = խոսափող.
- recording = ձայնագրում.
- memories = հիշողություններ.
- chat = զրույց.
- troubleshooting = խնդիրների վերացում / ախտորոշում.

Need maybe mention BasedHardware/omi CLI. Could include "OMI CLI-ը BasedHardware/omi նախագծի...".

Need ensure all explanatory Armenian. Code English. Could include inline code English. Armenian punctuation. Need maybe use Armenian em dash? Fine.

Potential issue: Armenian word for "pip" maybe keep. "Python 3.10+".

Need maybe include "Օգտագործեք վիրտուալ միջավայր". Armenian: "Խորհուրդ է տրվում օգտագործել վիրտուալ միջավայր".

Need maybe include "Ստուգեք տեղադրումը": `omi --version`? Not in core commands but okay. Could include.

Need maybe include "Սարքը պատրաստելու համար": `omi setup`.

Need maybe include "Եթե սարքը չի հայտնաբերվում...".

Need maybe include "Ձայնագրված ֆայլերը...". But don't invent paths? Could say "սովորաբար նշվում է հրամանի արդյունքում".

Need maybe include "Հիշողությունների կառավարում" examples: `omi memories --help`, `omi memories list`? If not documented, maybe avoid specific subcommands except core. But examples can be generic? User says core commands and examples. Could show `omi memories` and `omi memories --help`. For chat: `omi chat` and `omi chat "..."`. For record: `omi record`. For listen: `omi listen`.

Need maybe include "Ստուգեք, որ OMI սարքը միացված է և տեսանելի է համակարգչին". Armenian.

Need maybe include "Միկրոֆոնի թույլտվություն". Armenian: "Խոսափողի թույլտվություն".

Need maybe include "Օգտագործեք `omi --help`".

Need maybe include "Ստուգեք Python-ի տարբերակը": `python --version`.

Need maybe include "Ստուգեք pip-ը": `pip --version`.

Need maybe include "Տեղադրեք օգտատիրոջ մակարդակով": `pip install --user omi-cli`.

Need maybe include "PATH-ում ավելացրեք pip-ի օգտատիրոջ bin թղթապանակը". Armenian: "ավելացրեք ... PATH միջավայրի փոփոխականում".

Need maybe include "Եթե օգտագործում եք macOS/Linux". Armenian.

Need maybe include "Windows-ում PowerShell".

Need maybe include "Սարքի հավատարմագրում". Could mention "հաշիվ/հավատարմագրեր". But not know auth details. Keep generic.

Need maybe include "Նախքան օգտագործումը կարդացեք BasedHardware/omi փաստաթղթերը". Armenian.

Need ensure no Chinese. All Armenian.

Let's draft final:

# OMI CLI Quickstart (Հայերեն)

OMI CLI-ը BasedHardware/omi նախագծի հրամանային գործիքն է...

## Նախապես պահանջվող պայմաններ (Prerequisites)
- Python 3.10+
- pip
- ...

Maybe "Նախապես պահանջվող պայմաններ" unnatural? "Նախապատրաստական պահանջներ". Use that.

## Տեղադրում (Installation)
...

## Սարքի զույգում և հավատարմագրում (Pairing & Auth)
...

## Հիմնական հրամաններ (Core Commands)
### Իրական ժամանակում լսում և վերծանում
...

## Խնդիրների վերացում (Troubleshooting)
...

Need maybe include "Օգտագործման օրինակներ".

Need maybe include "Ստուգեք, որ `omi` հրամանը հասանելի է".

Need maybe include "Եթե `command not found`". Armenian: "Եթե ստանում եք `command not found` սխալը".

Need maybe include "Եթե խոսափողը չի աշխատում".

Need maybe include "Եթե սարքը չի զույգվում".

Need maybe include "Եթե հիշողությունները չեն երևում".

Need maybe include "Օգտագործեք `omi --help`".

Need maybe include "Միջավայրի փոփոխականներ"? Not necessary.

Need maybe include "Ձայնագրումների համար օգտագործեք `omi record`".

Need maybe include "Զրույցի համար `omi chat`".

Need maybe include "Օգտագործեք `omi memories` հիշողությունները դիտելու/կառավարելու համար".

Need maybe include "Օգտ