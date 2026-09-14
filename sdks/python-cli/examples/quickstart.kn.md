# omi-cli ಕನ್ನಡ ತ್ವರಿತ ಆರಂಭ ಮಾರ್ಗದರ್ಶಿ (Kannada Quickstart Guide)

> ಟರ್ಮಿನಲ್‌ನಿಂದ Omi ಜೊತೆ ಸಂವಹನ ನಡೆಸಲು ಪ್ರಾಯೋಗಿಕ ಮಾರ್ಗದರ್ಶಿ. ಡೆವಲಪರ್‌ಗಳು ಮತ್ತು AI ಏಜೆಂಟ್‌ಗಳು ಇಬ್ಬರಿಗೂ ಉಪಯುಕ್ತ.

`omi-cli` ಎಂಬುದು [Omi](https://omi.me) ಡೆವಲಪರ್ API ಬಳಸಲು ಅಧಿಕೃತ ಕಮಾಂಡ್-ಲೈನ್ ಇಂಟರ್‌ಫೇಸ್ (CLI) ಆಗಿದೆ. Omi ನಲ್ಲಿರುವ ನಾಲ್ಕು ಪ್ರಮುಖ ಸಂಪನ್ಮೂಲಗಳನ್ನು (ನೆನಪುಗಳು, ಸಂಭಾಷಣೆಗಳು, ಕ್ರಿಯಾ ಐಟಂಗಳು ಮತ್ತು ಗುರಿಗಳು) ಸಮರ್ಥವಾಗಿ ನಿರ್ವಹಿಸಲು ಮತ್ತು ಸ್ಕ್ರಿಪ್ಟ್‌ಗಳ ಮೂಲಕ ಆಟೋಮೇಷನ್ ಮಾಡಲು ಇದು ಸಹಾಯ ಮಾಡುತ್ತದೆ.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **ಅಧಿಕೃತ ದಾಖಲಾತಿ:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **ಮೂಲ ಕೋಡ್:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. ಸ್ಥಾಪನೆ (Installation)

ಇತರ ಪೈಥಾನ್ ಪ್ಯಾಕೇಜ್‌ಗಳಿಂದ ಪ್ರತ್ಯೇಕವಾಗಿರಿಸಲು `pipx` ಬಳಸಿ ಇನ್‌ಸ್ಟಾಲ್ ಮಾಡುವುದು ಅತ್ಯುತ್ತಮ ವಿಧಾನ:

```bash
# ಶಿಫಾರಸು ಮಾಡಲಾದ ವಿಧಾನ: pipx ಮೂಲಕ ಸ್ಥಾಪನೆ
pipx install omi-cli

# ಅಥವಾ pip ಬಳಸುವ ಮೂಲಕ
pip install omi-cli
```

> **ಪ್ರಮುಖ ಸೂಚನೆ: ಪ್ಯಾಕೇಜ್ ಹೆಸರು ಮತ್ತು ಕಮಾಂಡ್ ಹೆಸರು ನಡುವಿನ ವ್ಯತ್ಯಾಸ**
> * ಪೈಥಾನ್ ಪ್ಯಾಕೇಜ್ ಹೆಸರು **`omi-cli`** ಆಗಿದೆ (PyPI ನಲ್ಲಿರುವ `omi` ಬೇರೆ ಸಂಬಂಧವಿಲ್ಲದ ಪ್ಯಾಕೇಜ್, ಅದನ್ನು ಇನ್‌ಸ್ಟಾಲ್ ಮಾಡಬೇಡಿ).
> * ಇನ್‌ಸ್ಟಾಲ್ ಮಾಡಿದ ನಂತರ ಟರ್ಮಿನಲ್‌ನಲ್ಲಿ ಚಲಾಯಿಸುವ ಕಮಾಂಡ್ ಹೆಸರು **`omi`** ಆಗಿದೆ.

ಸ್ಥಾಪನೆ ಪೂರ್ಣಗೊಂಡ ನಂತರ ಆವೃತ್ತಿ ಮತ್ತು ಸಹಾಯ ಮಾಹಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಿ:

```bash
omi --version
omi --help
```

---

## 2. ದೃಢೀಕರಣ (Authentication)

`omi-cli` ಎರಡು ರೀತಿಯ ದೃಢೀಕರಣ ವಿಧಾನಗಳನ್ನು ಬೆಂಬಲಿಸುತ್ತದೆ:

| ವಿಧಾನ | ಮುಖ್ಯ ಉಪಯೋಗ | ಉದಾಹರಣೆ ಕಮಾಂಡ್ |
| :--- | :--- | :--- |
| **ಡೆವಲಪರ್ API ಕೀ (`omi_dev_*`)** | CI/CD, ಆಟೋಮೇಷನ್ ಸ್ಕ್ರಿಪ್ಟ್‌ಗಳು, AI ಏಜೆಂಟ್‌ಗಳು | `omi auth login --api-key ...` ಅಥವಾ ಎನ್ವಿರಾನ್‌ಮೆಂಟ್ ವೇರಿಯೇಬಲ್ಸ್ |
| **ಬ್ರೌಸರ್ OAuth (Google/Apple)** | ಡೆವಲಪರ್ ವೈಯಕ್ತಿಕ ಲ್ಯಾಪ್‌ಟಾಪ್ / ಕಂಪ್ಯೂಟರ್ | `omi auth login --browser` |

### ಇಂಟರಾಕ್ಟಿವ್ ಲಾಗಿನ್ (Interactive Login)
ಯಾವುದೇ ಫ್ಲ್ಯಾಗ್ ಇಲ್ಲದೆ ಕಮಾಂಡ್ ಚಲಾಯಿಸಿದರೆ ಬ್ರೌಸರ್ ಅಥವಾ API ಕೀ ಆಯ್ಕೆ ಮಾಡುವ ಅವಕಾಶ ಸಿಗುತ್ತದೆ:

```bash
omi auth login
# 1) Browser — Google ಅಥವಾ Apple ಖಾತೆಯ ಮೂಲಕ ಲಾಗಿನ್ ಆಗಿ (ವ್ಯಕ್ತಿಗಳಿಗಾಗಿ)
# 2) API key — app.omi.me ನಿಂದ ಪಡೆದ ಡೆವಲಪರ್ ಕೀ ನಮೂದಿಸಿ (ಏಜೆಂಟ್‌ಗಳು/CI ಗಾಗಿ)
```

### ನೇರವಾಗಿ ಬ್ರೌಸರ್ ಮೂಲಕ ಲಾಗಿನ್
```bash
omi auth login --browser
```

### API ಕೀ ಬಳಸುವುದು
[app.omi.me](https://app.omi.me) ನಲ್ಲಿ "Developer → API Keys" ವಿಭಾಗದಿಂದ ಡೆವಲಪರ್ ಕೀ ಪಡೆದು ಹೊಂದಿಸಿ:

```bash
# ಕಮಾಂಡ್ ಮೂಲಕ ಹೊಂದಿಸಿ
omi auth login --api-key omi_dev_...

# ಅಥವಾ ಎನ್ವಿರಾನ್‌ಮೆಂಟ್ ವೇರಿಯೇಬಲ್ ಮೂಲಕ ಹೊಂದಿಸಿ (CI/CD ಗಾಗಿ ಉತ್ತಮ)
export OMI_API_KEY=omi_dev_...
```

### ದೃಢೀಕರಣ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸುವುದು
* `omi auth status`: ಸ್ಥಳೀಯ ಪ್ರೊಫೈಲ್, ಮರೆಮಾಡಲಾದ ಟೋಕನ್ ಮತ್ತು ಮುಕ್ತಾಯ ವಿವರಗಳನ್ನು ತೋರಿಸುತ್ತದೆ (ಆಫ್‌ಲೈನ್‌ನಲ್ಲಿ ಕಾರ್ಯನಿರ್ವಹಿಸುತ್ತದೆ).
* `omi auth whoami`: ಸರ್ವರ್‌ಗೆ ನೇರ ವಿನಂತಿ ಕಳುಹಿಸಿ ಕೀ ಮಾನ್ಯವಾಗಿದೆಯೇ ಎಂದು ಖಚಿತಪಡಿಸುತ್ತದೆ (ಇಂಟರ್ನೆಟ್ ಅಗತ್ಯವಿದೆ).

```bash
omi auth status
omi auth whoami
```

ರುಜುವಾತುಗಳನ್ನು ತೆಗೆದುಹಾಕಲು ಲಾಗ್‌ಔಟ್ ಮಾಡಿ:
```bash
omi auth logout
```

ಕಾನ್ಫಿಗರೇಶನ್ ಫೈಲ್ ಪೂರ್ವನಿಯೋಜಿತವಾಗಿ `~/.omi/config.toml` ನಲ್ಲಿ ಸುರಕ್ಷಿತವಾಗಿ ಸಂಗ್ರಹವಾಗುತ್ತದೆ. ಇದನ್ನು ಯಾರೊಂದಿಗೂ ಹಂಚಿಕೊಳ್ಳಬೇಡಿ.

---

## 3. ಮೂಲಭೂತ ಬಳಕೆ (Basic Usage)

Omi ನಲ್ಲಿರುವ ನಾಲ್ಕು ಪ್ರಮುಖ ಸಂಪನ್ಮೂಲಗಳನ್ನು ನಿರ್ವಹಿಸುವುದು:

### ನೆನಪುಗಳು (Memories)
ವ್ಯವಸ್ಥೆ ಕಲಿತ ಸತ್ಯಗಳು ಮತ್ತು ಮಾಹಿತಿಯನ್ನು ನಿರ್ವಹಿಸಿ:

```bash
# ನೆನಪುಗಳ ಪಟ್ಟಿಯನ್ನು ವೀಕ್ಷಿಸಿ
omi memory list

# ಹೊಸ ನೆನಪನ್ನು ರಚಿಸಿ
omi memory create "ಬಳಕೆದಾರರು ಡಾರ್ಕ್ ಮೋಡ್ ಇಷ್ಟಪಡುತ್ತಾರೆ" --category lifestyle

# ನಿರ್ದಿಷ್ಟ ನೆನಪಿನ ವಿವರಗಳನ್ನು ಪಡೆಯಿರಿ
omi memory get <MEMORY_ID>
```

### ಸಂಭಾಷಣೆಗಳು (Conversations)
ಧರಿಸಬಹುದಾದ ಸಾಧನ ಅಥವಾ ಆಪ್‌ನಿಂದ ರೆಕಾರ್ಡ್ ಮಾಡಲಾದ ಆಡಿಯೋ ಮತ್ತು ಟ್ರಾನ್ಸ್‌ಕ್ರಿಪ್ಟ್‌ಗಳು:

```bash
# ಇತ್ತೀಚಿನ 5 ಸಂಭಾಷಣೆಗಳನ್ನು ನೋಡಿ
omi conversation list --limit 5

# ಸಂಭಾಷಣೆ ವಿವರಗಳು ಮತ್ತು ಪೂರ್ಣ ಟ್ರಾನ್ಸ್‌ಕ್ರಿಪ್ಟ್ ಪಡೆಯಿರಿ
omi conversation get <CONVERSATION_ID> --include-transcript
```

### ಕ್ರಿಯಾ ಐಟಂಗಳು (Action Items)
ಸಂಭಾಷಣೆಗಳಿಂದ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಗುರುತಿಸಲಾದ ಕಾರ್ಯಗಳು:

```bash
# ಪೂರ್ಣಗೊಳ್ಳದ ಕಾರ್ಯಗಳ ಪಟ್ಟಿಯನ್ನು ಮಾತ್ರ ನೋಡಿ
omi action-item list --open

# ಕಾರ್ಯ ಪೂರ್ಣಗೊಂಡಿದೆ ಎಂದು ಗುರುತಿಸಿ
omi action-item complete <ACTION_ITEM_ID>
```

### ಗುರಿಗಳು (Goals)
ಟ್ರ್ಯಾಕ್ ಮಾಡಲಾಗುತ್ತಿರುವ ಗುರಿಗಳನ್ನು ವೀಕ್ಷಿಸಿ:

```bash
# ಗುರಿಗಳ ಪಟ್ಟಿಯನ್ನು ನೋಡಿ
omi goal list
```

---

## 4. ಸ್ಕ್ರಿಪ್ಟಿಂಗ್ ಮತ್ತು JSON ಔಟ್‌ಪುಟ್ (`--json`)

`omi-cli` ನೇರ JSON ಔಟ್‌ಪುಟ್ ಬೆಂಬಲಿಸುತ್ತದೆ. `jq` ಅಥವಾ ಇತರ ಪ್ರೋಗ್ರಾಂಗಳೊಂದಿಗೆ ಬಳಸುವಾಗ `--json` ಗ್ಲೋಬಲ್ ಆಯ್ಕೆಯನ್ನು **ಸಬ್-ಕಮಾಂಡ್‌ಗಿಂತ ಮೊದಲೇ** ನೀಡಬೇಕು:

```bash
# ನೆನಪುಗಳನ್ನು JSON ನಲ್ಲಿ ಪಡೆದು ID ಮತ್ತು ವಿವರಗಳನ್ನು ಪ್ರತ್ಯೇಕಿಸಿ
omi --json memory list | jq '.[] | {id, content, category}'

# ಇತ್ತೀಚಿನ ಸಂಭಾಷಣೆಗಳ ಶೀರ್ಷಿಕೆಗಳನ್ನು ನೋಡಿ
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# ಬಾಕಿ ಇರುವ ಕಾರ್ಯಗಳನ್ನು JSON ರೂಪದಲ್ಲಿ ನೋಡಿ
omi --json action-item list --open | jq '.'
```

> **ಪ್ರಮುಖ ನಿಯಮ:** `--json` ಧ್ವಜವನ್ನು ಯಾವಾಗಲೂ ಸಬ್-ಕಮಾಂಡ್‌ಗಿಂತ **ಮೊದಲು** ಇರಿಸಿ:
> * ಸರಿಯಾದದ್ದು: `omi --json memory list`
> * ತಪ್ಪು: `omi memory list --json`

### ಫೈಲ್‌ನಲ್ಲಿ ಉಳಿಸುವುದು ಮತ್ತು ಪುಟೀಕರಣ (Pagination)

```bash
# ಮೊದಲ 25 ದಾಖಲೆಗಳನ್ನು ಫೈಲ್‌ನಲ್ಲಿ ಉಳಿಸಿ
omi --json memory list --limit 25 --offset 0 > nenapugalu-page-1.json

# ಮುಂದಿನ 25 ದಾಖಲೆಗಳನ್ನು ಪಡೆಯಿರಿ
omi --json memory list --limit 25 --offset 25 > nenapugalu-page-2.json
```

---

## 5. ಎಕ್ಸಿಟ್ ಕೋಡ್‌ಗಳು (Exit Codes)

ಆಟೋಮೇಷನ್ ಸ್ಕ್ರಿಪ್ಟ್‌ಗಳಲ್ಲಿ ದೋಷಗಳನ್ನು ಪತ್ತೆಹಚ್ಚಲು ಕೆಳಗಿನ ಎಕ್ಸಿಟ್ ಕೋಡ್‌ಗಳು ಉಪಯುಕ್ತವಾಗಿವೆ:

| ಕೋಡ್ | ಪ್ರಕಾರ | ವಿವರಣೆ |
| :---: | :--- | :--- |
| `0` | Success | ಕಮಾಂಡ್ ಯಶಸ್ವಿಯಾಗಿ ಪೂರ್ಣಗೊಂಡಿದೆ |
| `1` | Usage Error | ಅಮಾನ್ಯ ಫ್ಲ್ಯಾಗ್‌ಗಳು ಅಥವಾ ಅಪೂರ್ಣ ನಿಯತಾಂಕಗಳು |
| `2` | Auth Error | ಲಾಗಿನ್ ಆಗಿಲ್ಲ, ಅಮಾನ್ಯ API ಕೀ ಅಥವಾ ಟೋಕನ್ ಮುಕ್ತಾಯಗೊಂಡಿದೆ |
| `3` | Server Error | ಸರ್ವರ್ ದೋಷ (5xx), ನೆಟ್‌ವರ್ಕ್ ಸಮಸ್ಯೆ ಅಥವಾ ಸಮಯ ಮೀರುವಿಕೆ (Timeout) |
| `4` | Rate Limited | ವಿನಂತಿ ಮಿತಿ ಮೀರಿದೆ (429 Too Many Requests) |
| `5` | Not Found | ವಿನಂತಿಸಿದ ಸಂಪನ್ಮೂಲ ಕಂಡುಬಂದಿಲ್ಲ (404 Not Found) |

---

## 6. ಶೆಲ್ ಎನ್ವಿರಾನ್‌ಮೆಂಟ್ ವೇರಿಯೇಬಲ್ಸ್ ಮಾದರಿಗಳು

### Bash / Zsh (Linux / macOS)
```bash
# API ಕೀ ಹೊಂದಿಸಿ
export OMI_API_KEY="omi_dev_your_actual_key_here"

# ಕಮಾಂಡ್ ಚಲಾಯಿಸಿ
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API ಕೀ ಹೊಂದಿಸಿ
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# PowerShell ನಲ್ಲಿ JSON ಪಾರ್ಸಿಂಗ್
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. ಸ್ಥಳೀಯ ಡೆಸ್ಕ್‌ಟಾಪ್ API ಜೊತೆ ಸಂಯೋಜನೆ (Local Desktop API)

Omi Desktop ಆಪ್ ಚಾಲನೆಯಲ್ಲಿರುವಾಗ, ಕ್ಲೌಡ್ ಅಗತ್ಯವಿಲ್ಲದೆ ಕಂಪ್ಯೂಟರ್‌ನಲ್ಲಿರುವ ಡೇಟಾವನ್ನು ನೇರವಾಗಿ ಹುಡುಕಬಹುದು:

```bash
# ಸ್ಥಳೀಯ API ವಿಳಾಸ ಮತ್ತು ಟೋಕನ್ ಕಾನ್ಫಿಗರ್ ಮಾಡಿ
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# ಸ್ಥಳೀಯ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಿ
omi --json local status

# ಸ್ಕ್ರೀನ್ ಇತಿಹಾಸದಲ್ಲಿ ಹುಡುಕಿ
omi --json local search-screen "ಪ್ರಾಜೆಕ್ಟ್ ಯೋಜನೆ" --days 7 --app Safari
```

---

## 8. ಪ್ರೊಫೈಲ್‌ಗಳ ನಿರ್ವಹಣೆ (Profiles)

ಹಲವು ಖಾತೆಗಳು ಅಥವಾ ಪರೀಕ್ಷಾ ಪರಿಸರಗಳನ್ನು ನಿರ್ವಹಿಸಲು `--profile` ಆಯ್ಕೆಯನ್ನು ಬಳಸಿ:

```bash
# ವೈಯಕ್ತಿಕ ಪ್ರೊಫೈಲ್‌ನೊಂದಿಗೆ ಲಾಗಿನ್ ಆಗಿ
omi --profile personal auth login

# ಕಚೇರಿ ಪ್ರೊಫೈಲ್‌ನೊಂದಿಗೆ ಲಾಗಿನ್ ಆಗಿ
omi --profile work auth login

# ಇಷ್ಟವಿರುವ ಪ್ರೊಫೈಲ್ ಅಡಿಯಲ್ಲಿ ಕಮಾಂಡ್‌ಗಳನ್ನು ಚಲಾಯಿಸಿ
omi --profile work memory list
```
