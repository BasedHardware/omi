# 开始，不要前言。需要作为开源资深技术布道专家，为 BasedHardware/omi CLI 工具撰写 Azerbaijani 语言专属快速上手指南。需要包含标题、前置要求、安装、设备配对与认证、常用核心命令与示例、常见问题与排错。命令与代码保持英文。全部说明文字用 Azerbaijani。需要确保 Markdown 完整。

需要思考 Azerbaijani 术语。用户要求“原汁原味 Azerbaijani（Azərbaycanca）语言专属快速上手指南”。标题指定：# OMI CLI Quickstart (Azərbaycanca)。虽然标题含英文 Quickstart，但要求如此。

需要避免前言。直接输出 Markdown。

需要确保命令：pip install omi-cli, omi setup, omi listen, omi record, omi memories, omi chat。可能示例：omi listen --language az? 但项目背景未给参数，不要编造过多？可以写通用示例，但避免不存在的参数。可以写 `omi listen`，`omi record --output recording.wav`? 不确定。最好只使用给定命令，或加安全示例如 `omi chat "Sualınız"`? 但 CLI 可能支持？ BasedHardware/omi CLI 实际？ 我需要谨慎。用户只给核心命令，不要求参数。可以示例：`omi chat` 进入对话，或 `omi chat "..."` 可能合理，但可能不存在。为了安全，示例只展示命令本身，或说明“（若支持）”？ 但快速指南需要示例。可以写：
```bash
omi chat
```
然后输入问题。避免参数。

需要 Azerbaijani 地道。术语：
- Prerequisites: Tələblər / Ön şərtlər. 用户指定英文括号 Prerequisites: Python 3.10+, pip。可以标题：## Ön şərtlər (Prerequisites)
- Installation: Quraşdırma
- Pairing & Auth: Cihazın qoşulması və autentifikasiya / Cihazın cütləşdirilməsi və kimlik doğrulama. Azerbaijani: “Cihazın qoşulması və autentifikasiya” 或 “Cihazın cütləşdirilməsi və autentifikasiya”. “Pairing” 常用 “qoşulma” / “cütləşdirmə”. 用 “Cihazın qoşulması və autentifikasiya (Pairing & Auth)”.
- Core Commands: Əsas əmrlər və nümunələr
- Troubleshooting: Tez-tez rast gəlinən problemlər və həll yolları / Problemlərin aradan qaldırılması.

需要说明文字 Azerbaijani。命令代码英文。

可能内容：
# OMI CLI Quickstart (Azərbaycanca)

Bu sənəd BasedHardware/omi CLI alətini ilk dəfə istifadə edən tərtibatçılar və istifadəçilər üçün nəzərdə tutulub.

## Ön şərtlər (Prerequisites)
- Python 3.10 və ya daha yeni versiya
- pip (Python paket meneceri)
- İnternet bağlantısı
- OMI cihazı və ya emulator? 项目可穿戴硬件。可以写 “OMI cihazı (və ya uyğun emulator)”.
- Mikrofon icazələri.

Qeyd: virtual mühit tövsiyə olunur.
```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
```
命令英文，注释可 Azerbaijani? 代码注释可以 Azerbaijani? 用户说命令与代码保持英文。注释可能算代码？ 为安全，代码块内只命令，注释可英文？ 但说明文字 Azerbaijani。代码块内注释若英文更符合要求。可以不用注释。

## Quraşdırma (Installation)
```bash
pip install omi-cli
```
Yoxlama:
```bash
omi --version
```
If not installed? 说明 Azerbaijani.

## Cihazın qoşulması və autentifikasiya (Pairing & Auth)
```bash
omi setup
```
Bu əmr cihazı qoşur, istifadəçi hesabını doğrulayır və lokal konfiqurasiya yaradır.
Addımlar:
1. Cihazı Bluetooth/Wi-Fi ilə aktiv edin.
2. `omi setup` əmrini icra edin.
3. Təlimatlara uyğun olaraq cihazı seçin.
4. Kimlik doğrulama tamamlandıqda `~/.omi` və ya oxşar konfiqurasiya qovluğu yaradıla bilər. 不确定路径，避免具体。可以写 “lokal konfiqurasiya saxlanılır”.

## Əsas əmrlər və nümunələr (Core Commands)
Table:
| Əmr | Təsvir |
| `omi listen` | Real vaxt rejimində transkripsiya və dinləmə |
...
Examples:
```bash
omi listen
```
```bash
omi record
```
```bash
omi memories
```
```bash
omi chat
```
Maybe `omi chat` interactive.

Need maybe “Sessiyaya başlamaq üçün” etc.

## Troubleshooting
- `omi: command not found`: pip path not in PATH; reinstall, use `python -m pip install --user omi-cli`, check PATH.
- Python version: `python --version` must 3.10+.
- microphone permission: macOS/Windows/Linux allow.
- Bluetooth pairing: device not found, ensure device on, close other apps, restart `omi setup`.
- network/auth: check internet, re-run `omi setup`.
- logs: maybe `omi --help`? Use `omi --help` and `omi <command> --help`? If not known? CLI likely supports --help. Safe.

Need Azerbaijani grammar. Let's craft polished Azerbaijani.

Potential Azerbaijani text:
“Bu bələdçi, BasedHardware/omi CLI alətini quraşdırmaq, OMI cihazını qoşmaq və əsas əmrlərlə ilk nəticəni almaq üçün nəzərdə tutulub.”

“Quraşdırma” section:
“Tövsiyə olunan yanaşma: layihə üçün ayrıca virtual mühit istifadə edin.”
Code:
```bash
python -m venv .venv
source .venv/bin/activate
```
Windows:
```bash
.venv\Scripts\activate
```
Then install.

Need “pip” maybe `pip3`? Use `pip`.

“Cihazın qoşulması və autentifikasiya”:
“`omi setup` interaktiv quraşdırma axınıdır. O, cihazı aşkarlayır, istifadəçi hesabını doğrulayır və lokal konfiqurasiya faylını yaradır.”
“Cihazı qoşmadan əvvəl:”
- “OMI cihazını açın və qoşulma rejiminə keçirin.”
- “Kompüterdə Bluetooth/Wi-Fi aktiv olsun.”
- “İlk dəfə istifadə edirsinizsə, `omi setup` əmrini icra edin.”

“Core Commands”:
Maybe include “Real vaxt transkripsiyası” etc.

Need ensure all explanatory text Azerbaijani. Some English terms like CLI, pip, Bluetooth, Wi-Fi, macOS, Windows, Linux, PATH, virtual environment? Azerbaijani can use “virtual mühit”. “PATH” maybe “PATH mühit dəyişəni”.

Need no draft. final only markdown.

Double-check Azerbaijani diacritics: ə, ğ, ı, ö, ş, ü, ç. Use correct.

Potential final:

# OMI CLI Quickstart (Azərbaycanca)

Bu bələdçi BasedHardware/omi CLI alətini quraşdırmaq, OMI cihazını qoşmaq və əsas əmrlərlə ilk nəticəni almaq üçün nəzərdə tutulub.

## Ön şərtlər (Prerequisites)

- Python 3.10 və ya daha yeni versiya
- `pip` paket meneceri
- İnternet bağlantısı
- OMI cihazı və ya uyğun test mühiti
- Mikrofon və qoşulma icazələri

Tövsiyə olunan quraşdırma üsulu: virtual mühit.

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows üçün:

```bash
.venv\Scripts\activate
```

## Quraşdırma (Installation)

CLI paketini quraşdırın:

```bash
pip install omi-cli
```

Quraşdırmanın işlədiyini yoxlayın:

```bash
omi --version
```

Əgər `omi` əmri tapılmırsa, `pip` quraşdırma qovluğunun `PATH` mühit dəyişəninə əlavə olunduğundan əmin olun.

## Cihazın qoşulması və autentifikasiya (Pairing & Auth)

İlk istifadə zamanı cihazı qoşmaq və hesabı doğrulamaq üçün:

```bash
omi setup
```

Bu əmr interaktiv quraşdırma axını açır və aşağıdakıları yerinə yetirir:

1. OMI cihazını aşkarlayır.
2. İstifadəçi hesabını doğrulayır.
3. Lokal konfiqurasiya saxlayır.
4. Növbəti əmrlər üçün cihazı hazır vəziyyətə gətirir.

Qoşulma zaman