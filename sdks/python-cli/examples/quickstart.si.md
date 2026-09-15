# omi-cli ඉක්මන් ආරම්භක මාර්ගෝපදේශය (Sinhala Quickstart)

> Terminal එකෙන් කෙලින්ම Omi සමඟ වැඩ කිරීම සඳහා ප්‍රායෝගික මාර්ගෝපදේශයක් — සංවර්ධකයින් සහ ස්වයංක්‍රීය AI agent සඳහා.

`omi-cli` යනු [Omi](https://omi.me) developer API සඳහා නිල command-line interface එකයි. එමඟින් පද්ධතියේ මූලික කොටස් හතර ව්‍යුහගත හා ස්වයංක්‍රීය කළ හැකි ආකාරයෙන් කළමනාකරණය කළ හැක: මතකයන් (memories), සංවාද (conversations), ක්‍රියාකාරී අයිතම (action items) සහ ඉලක්ක (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **නිල ලේඛන:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **මූල කේතය:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Command නම්, option සහ වැඩසටහනේ පණිවිඩ ඉංග්‍රීසියෙන්ම පවතී; මෙම මාර්ගෝපදේශයේ පැහැදිලි කිරීමේ පෙළ පමණක් සිංහලෙන් ලියා ඇත. ඉංග්‍රීසි README ප්‍රධාන යොමුවයි.

---

## 1. ස්ථාපනය

Dependency ගැටුම් වළක්වා CLI එක වෙන් වූ පරිසරයක ධාවනය කිරීමට `pipx` නිර්දේශ කෙරේ:

```bash
# නිර්දේශිත: pipx මඟින් වෙන් වූ ස්ථාපනය
pipx install omi-cli

# විකල්පය: සක්‍රිය Python virtual environment එකක් තුළ pip මඟින්
pip install omi-cli
```

> **සටහන: Package නම සහ command නම**
> * PyPI හි package නම **`omi-cli`** වේ (`omi` යන නම අදාළ නොවන package එකකට අයත් වේ).
> * Terminal එකේ ඔබ ධාවනය කරන command එක **`omi`** පමණි.

ස්ථාපනය ක්‍රියා කරන බව තහවුරු කරගන්න:

```bash
omi --version
omi --help
```

Terminal එකට `omi` සොයාගත නොහැකි නම්, virtual environment එක සක්‍රිය බව හෝ `pipx` විසින් executable තබන directory එක ඔබේ `PATH` හි ඇති බව පරීක්ෂා කරන්න.

---

## 2. සත්‍යාපනය (Authentication)

`omi-cli` ප්‍රධාන සත්‍යාපන ක්‍රම දෙකකට සහාය දක්වයි:

| ක්‍රමය | භාවිත අවස්ථාව | උදාහරණය |
| :--- | :--- | :--- |
| **Developer API යතුර (`omi_dev_*`)** | Script, CI/CD, headless server, AI agent | `omi auth login --api-key ...` හෝ `OMI_API_KEY` |
| **Browser OAuth (Google/Apple)** | දේශීය වැඩපොළ සහ සංවර්ධකයින් | `omi auth login --browser` (Google) / `--provider apple` |

### අන්තර්ක්‍රියාකාරී පිවිසුම
ක්‍රමය අන්තර්ක්‍රියාකාරීව තෝරාගැනීමට කිසිදු flag එකක් නොමැතිව ධාවනය කරන්න:

```bash
omi auth login
# 1) Browser — Google පිවිසුම සඳහා browser එක විවෘත කරයි (Apple සඳහා `--provider apple` භාවිතා කරන්න)
# 2) API key — app.omi.me වෙතින් API යතුර paste කරන්න (ඇතුළත් කිරීම සඟවා ඇත)
```

### Browser මඟින් සෘජු පිවිසුම
```bash
# පෙරනිමිය: Google පිවිසුම
omi auth login --browser

# විකල්පය: Apple පිවිසුම
omi auth login --browser --provider apple
```

### Developer API යතුරක් භාවිතය
[app.omi.me](https://app.omi.me) හි **Developer → API Keys** යටතේ යතුරක් සාදන්න:

```bash
# යතුර සක්‍රිය දේශීය profile එකේ ගබඩා කරන්න
omi auth login --api-key omi_dev_ඔබේ_සැබෑ_token

# නැතහොත් environment variable එකක් ලෙස සකසන්න (container සහ CI/CD සඳහා හොඳම)
export OMI_API_KEY="omi_dev_ඔබේ_සැබෑ_token"
```

> `OMI_API_KEY` භාවිතා වන්නේ සක්‍රිය profile එකේ ගබඩා කළ යතුරක් නොමැති විට පමණි. ඔබ දැනටමත් `omi auth login` මඟින් පිවිස ඇත්නම් සහ environment variable එක ක්‍රියාත්මක වීමට අවශ්‍ය නම්, පළමුව `omi auth logout` ධාවනය කරන්න.

### සත්‍යාපන තත්ත්වය පරීක්ෂා කිරීම
* `omi auth status`: සක්‍රිය profile එක සහ සඟවන ලද අක්තපත්‍ර පෙන්වයි (දේශීයව/offline ධාවනය වේ; කල් ඉකුත්වීමේ දිනය OAuth token සඳහා පමණක් අදාළ වේ).
* `omi auth whoami`: වලංගුභාවය තහවුරු කිරීමට Omi server වෙත ඉල්ලීමක් යවයි (ජාලය අවශ්‍යයි).

```bash
omi auth status
omi auth whoami
```

නැවත පිවිසීමකින් තොරව OAuth token එක අලුත් කිරීම:

```bash
omi auth refresh
```

> `omi auth refresh` ක්‍රියා කරන්නේ browser (OAuth) මඟින් පිවිසි profile සඳහා පමණි. API යතුර මත පදනම් profile සඳහා අලුත් කිරීමට කිසිවක් නොමැති අතර, command එක «Nothing to refresh» පණිවිඩය සහ exit code `1` සමඟ අවසන් වේ.

පිටවීම:
```bash
omi auth logout
# OMI_API_KEY environment එකේ සකසා ඇත්නම් එයද ඉවත් කරන්න (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. මූලික command

### මතකයන් (Memories)
Omi විසින් ගබඩා කර ඇති ව්‍යුහගත කරුණු සහ සන්දර්භීය නිරීක්ෂණ:

```bash
# මතකයන් ලැයිස්තුගත කරන්න
omi memory list

# කාණ්ඩයක් සමඟ නව මතකයක් සාදන්න
omi memory create "Python උදාහරණ සහිත කෙටි තාක්ෂණික පිළිතුරු කැමතියි" --category work

# ID මඟින් නිශ්චිත මතකයක් ලබාගන්න
omi memory get <MEMORY_ID>
```

### සංවාද (Conversations)
Omi උපාංග මඟින් වාර්තා කරන ලද හඬ පටිගත කිරීම්, පිටපත් සහ සංවාද:

```bash
# අවසන් සංවාද 5 ලැයිස්තුගත කරන්න
omi conversation list --limit 5

# සම්පූර්ණ පිටපත සමඟ සංවාදයක විස්තර ලබාගන්න
omi conversation get <CONVERSATION_ID> --include-transcript
```

### ක්‍රියාකාරී අයිතම (Action Items)
සංවාද වලින් ස්වයංක්‍රීයව උපුටාගත් කාර්යයන්:

```bash
# විවෘත ක්‍රියාකාරී අයිතම ලැයිස්තුගත කරන්න
omi action-item list --open

# ක්‍රියාකාරී අයිතමයක් සම්පූර්ණ කළ බව සලකුණු කරන්න
omi action-item complete <ACTION_ITEM_ID>
```

### ඉලක්ක (Goals)
ප්‍රගති දර්ශක සහ දිගුකාලීන ඉලක්ක:

```bash
# සක්‍රිය ඉලක්ක ලැයිස්තුගත කරන්න
omi goal list

# නව සංඛ්‍යාත්මක ඉලක්කයක් සාදන්න
omi goal create "දිනකට වතුර ලීටර් 2ක් බොන්න" --type numeric --target 2 --unit liters

# ඉලක්කයක වත්මන් අගය යාවත්කාලීන කරන්න (ID සහ නව අගය)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. ව්‍යුහගත ස්වයංක්‍රීයකරණය සහ JSON ප්‍රතිදානය (`--json`)

`omi-cli` pipeline සහ toolchain තුළ ස්වයංක්‍රීයකරණය සඳහා ගොඩනගා ඇත. ගෝලීය `--json` flag එක පිරිසිදු, යන්ත්‍රයට කියවිය හැකි JSON ලබා දෙයි:

```bash
# මතකයන් JSON ලෙස ලැයිස්තුගත කර jq මඟින් පෙරන්න
omi --json memory list | jq '.[] | {id, content, category}'

# අවසන් සංවාද වල මාතෘකා ලබාගන්න
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# සියලුම විවෘත ක්‍රියාකාරී අයිතම අමු JSON ලෙස බලන්න
omi --json action-item list --open | jq '.'
```

> **වැදගත් වාක්‍ය රීතිය:**
> `--json` යනු **ගෝලීය option** එකක් වන අතර එය subcommand එකට **පෙර** තැබිය යුතුය:
> * නිවැරදි: `omi --json memory list`
> * වැරදි: `omi memory list --json`

### පිටු බෙදීම (Pagination)
`list` command `--limit` සහ `--offset` සඳහා සහාය දක්වයි:

```bash
omi --json memory list --limit 50 --offset 50
```

### ගොනුවකට නිර්යාත කිරීම
ANSI වර්ණ හෝ පාලන අක්ෂර ගොනුවට ඇතුළු වීම වළක්වා ගැනීමට, shell එකේම stdout සෘජුවම යොමු කරන්න:

```bash
# මතකයන් සෘජුවම පිරිසිදු JSON ගොනුවකට නිර්යාත කරන්න
omi --json memory list > memories.json
```

---

## 5. Exit code (Exit Codes Contract)

CI/CD සහ script වල විශ්වාසදායක දෝෂ හැසිරවීම සඳහා `omi-cli` දැඩි exit code ගිවිසුමක් අනුගමනය කරයි (`omi_cli/errors.py` බලන්න):

| කේතය | නම | විස්තරය සහ උදාහරණය |
| :---: | :--- | :--- |
| `0` | **සාර්ථකයි (`EXIT_OK`)** | මෙහෙයුම දෝෂයකින් තොරව අවසන් විය. |
| `1` | **භාවිත දෝෂය (`EXIT_USAGE`)** | omi-cli හිම වලංගුකරණ දෝෂ: එකට භාවිතා කළ නොහැකි `--browser` සහ `--api-key`, අන්තර්ක්‍රියාකාරී පිවිසුමේ වලංගු නොවන තේරීමක්, stdin වෙතින් හිස් ඇතුළත් කිරීමක්, හෝ API යතුරු profile එකක `omi auth refresh`. |
| `2` | **සත්‍යාපන දෝෂය (`EXIT_AUTH`)** | අක්තපත්‍ර නොමැති හෝ වලංගු නොවන, හෝ session එක කල් ඉකුත් වී ඇත. සටහන: නොදන්නා flag එකක් හෝ නැති argument එකක් Click විසින්ම ප්‍රතික්ෂේප කරන අතර එයද කේතය `2` සමඟ පිටවේ. |
| `3` | **Server දෝෂය (`EXIT_SERVER`)** | Omi server වෙතින් HTTP 5xx හෝ ජාල බිඳවැටීමක්. |
| `4` | **වේග සීමාව (`EXIT_RATE_LIMITED`)** | HTTP 429 — කෙටි කාලයක් තුළ ඉල්ලීම් වැඩිය. |
| `5` | **හමු නොවීය (`EXIT_NOT_FOUND`)** | HTTP 404 — ඉල්ලූ සම්පත (මතකය, සංවාදය, ක්‍රියාකාරී අයිතමය) නොපවතී. |

---

## 6. විවිධ shell සඳහා උදාහරණ

### Bash / Zsh (Linux / macOS)
```bash
# මෙම session එක සඳහා API යතුර සකසන්න
export OMI_API_KEY="omi_dev_ඔබේ_සැබෑ_token"

# Command එක ධාවනය කර exit code එක පරීක්ෂා කරන්න
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Omi වෙතින් මතකයන් ලබාගැනීමේ දෝෂයක්." >&2
fi
```

### PowerShell (Windows)
```powershell
# PowerShell හි environment variable එකක් අර්ථ දක්වන්න
$env:OMI_API_KEY = "omi_dev_ඔබේ_සැබෑ_token"

# JSON ප්‍රතිදානය සෘජුවම PowerShell object එකකට පරිවර්තනය කරන්න
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE මඟින් දෝෂ පරීක්ෂාව
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi command එක exit code $LASTEXITCODE සමඟ අසාර්ථක විය."
}
```

---

## 7. දේශීය Desktop API ඒකාබද්ධතාව (Omi Desktop)

Omi Desktop ඔබේ යන්ත්‍රයේ ධාවනය වන විට (පෙරනිමි port 47778), cloud හරහා නොගොස් දේශීය සන්දර්භය සමඟ සෘජුවම වැඩ කළ හැක:

```bash
# දේශීය API සම්බන්ධතාවය වින්‍යාස කරන්න (token ආරක්ෂා කිරීමට environment variable භාවිතා කරන්න)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token ඇතුළත් කරන්න: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# දේශීය සම්බන්ධතා තත්ත්වය තහවුරු කරන්න
omi --json local status

# දේශීය තිර ඉතිහාසයේ සොයන්න
omi --json local search-screen "කාර්තු වාර්තාව" --days 7 --app Safari
```

Environment variable වෙනුවට සැකසුම් profile එකේ ගබඩා කළ හැක: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Profile කිහිපයක් කළමනාකරණය (Profiles)

පුද්ගලික ගිණුම, රැකියා profile හෝ පරීක්ෂණ පරිසරය අතර පහසුවෙන් මාරු වීමට `--profile` භාවිතා කරන්න. සැකසුම් `~/.omi/config.toml` හි ගබඩා වේ. ප්‍රමුඛතා අනුපිළිවෙල: `--profile` flag එක, ඉන්පසු `OMI_PROFILE` environment variable එක, අවසානයේ `default` profile එක.

```bash
# පුද්ගලික profile එකක් සාදා පිවිසෙන්න
omi --profile personal auth login

# රැකියා profile එකක් සාදා පිවිසෙන්න
omi --profile work auth login

# නිශ්චිත profile එකක් සමඟ command එකක් ධාවනය කරන්න
omi --profile work memory list

# Environment variable එක මඟින් profile එක තෝරන්න
export OMI_PROFILE=work
omi memory list

# පරීක්ෂණ සඳහා අභිරුචි endpoint එකක් භාවිතා කරන්න
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. ආරක්ෂක මාර්ගෝපදේශ සහ හොඳම භාවිතයන්

* **යතුරු කේතයේ නොලියන්න:** API යතුරු (`omi_dev_*`) කිසිවිටෙක Git repository එකකට commit නොකරන්න. `.gitignore` හි ඇතුළත් `.env` ගොනු හෝ ආරක්ෂිත රහස් කළමනාකරු භාවිතා කරන්න.
* **Shell ඉතිහාසය ආරක්ෂා කරන්න:** හවුල් server වල යතුරු සෘජු command-line argument ලෙස ලබා නොදෙන්න; අන්තර්ක්‍රියාකාරී පිවිසුම හෝ `OMI_API_KEY` භාවිතා කරන්න.
* **Directory අවසර සීමා කරන්න:** Unix/macOS හි වින්‍යාස directory එකට සීමිත අවසර ඇති බව සහතික කරන්න:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Session පිරිසිදු කිරීම:** තාවකාලික පරිසර ඉවත් කරන විට environment variable එක ඉවත් කිරීමට මතක තබාගන්න:
  ```bash
  unset OMI_API_KEY
  ```
