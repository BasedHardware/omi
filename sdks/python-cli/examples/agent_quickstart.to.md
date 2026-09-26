# omi-cli maʻa e kau ʻākenga

> Fakahinohino ngāue maʻa e ngaahi meʻangāue ʻoku tataki ʻe he LLM (Claude Code, Cursor, hoʻo ngaahi bot).

## Ko e hā ʻoku faingofua ai ʻa e CLI ki he kau ʻākenga

* **Kontolaki JSON tuʻumaʻu.** ʻOku tuku ʻe `--json` ha tohi JSON kelei ʻi
  stdout — *ko e tohi JSON pē* — ʻikai ha fekau ʻoku hoko, ʻikai ha spinning.
  ʻAlu ʻa e ngaahi hala ki stderr ʻi he fōtunga `{"error": "...", "detail": "..."}`.
* **Ngaahi kouti ʻoku tuʻumaʻu.** `0` lelei / `1` ngāueʻanga / `2` fakamoʻoni /
  `3` sēva / `4` fakangatangata e leo / `5` ʻikai maʻu. ʻE lava ke vahevahe ʻe he
  kau ʻākenga ʻi he ngaahi kouti ni ʻo ʻikai fakaʻuhingaʻi ʻa e ngaahi hala lea
  fakanatula.
* **ʻIkai ha fehuʻi femahinoʻaki ʻi he ngaahi tūkunga headless.** Tuku ange `--yes`
  (pē `-y`) ki he ngaahi fekau fakapo; tuku ange `--api-key` pe fokotuʻu
  `OMI_API_KEY` ke fakalaka ʻi he hu ki loto.
* **ʻUlungaanga toe feinga fakakātaki.** ʻOku toe feinga ʻa `429` mo `5xx` mo e
  foki ki mui kimuʻa pea fakahā.

## Fakamoʻoni (taha pē, ʻe he tangata)

ʻOku maʻu ʻe he ʻūsā ha kī API dev mei he polokalama uepi ʻa Omi
(`https://app.omi.me` → Developer → API Keys) pea fili pē:

```bash
omi auth login                          # fakapipiki ʻa e nima; ʻoku ʻikai ʻi he hisitōlia shell ʻa e kī
# pe
export OMI_API_KEY=omi_dev_...          # fakataimi, lelei maʻa e puha
```

## Ko e ngaahi meʻa ʻe nima ʻoku lahi taha hono fai ʻe he kau ʻākenga

### 1. Lau ʻa e ngaahi manatu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Faʻu ha manatu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lau ʻa e ngaahi fetalanoaʻaki

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lau ʻa e ngaahi ngāue ʻoku ʻatā

```bash
omi action-item list --json --open
```

### 5. Fakaʻosi ha ngāue

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Fakalotofonua

ʻI he taimi ʻoku fakahā ai ʻe Omi Desktop hono API fakalotofonua, ʻe lava ke
fehuʻi ʻe he kau ʻākenga ki he hisitōlia ʻo e sioʻata ʻi he meʻangāue, ngaahi
fakamatala, SQL, mo e ngaahi ngāue ʻo ʻikai ngāueʻaki ʻa e API dev ʻo e ʻao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# pe, maʻa e ngaahi houa fakataimi:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

Fakaʻosi pē pe tāmateʻi ʻa e ngaahi ngāue ʻi he taimi pē ʻoku kole mahino ai ʻa
e ʻūsā:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

ʻOku tā ʻe `omi local screenshot SCREENSHOT_ID --output PATH` ʻa e sioʻata ki he
tisiki pea ʻoku ne toe paaki ʻa e JSON ki stdout maʻa e ngaahi tohi. Ko e ID ʻo
e sioʻata ʻoku maʻu mei `local search-screen` pe SQL ʻi he tepile
`screenshots`. Kapau ʻoku toe tuku mai ʻe Desktop ha hala fokotuʻutuʻu hangē ko
`screenshot_pending`, `screenshot_file_missing`, pe `screenshot_chunk_corrupted`,
ʻoku tauhi ʻe he fōtunga JSON ʻa e ngaahi konga `reason`, `hint`, mo
`screenshot_id` ʻi stderr koeʻuhi ke lava ʻe he kau ʻākenga ʻo toe feinga ʻi ha
ID motuʻa pe lipooti ʻa e faʻafitauli tonu. Fakamoʻoniʻi ʻa e ngaahi tuku ki tuʻa
ʻoku lelei ʻaki `file PATH` kimuʻa pea tuku ki he ngaahi meʻangāue sio.

## Fakatātā: sikalā ʻākenga Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ngāueʻaki ʻa e CLI omi ʻi he fōtunga JSON, fokotuʻu ha hala ʻi he kouti ʻoku ʻikai lelei."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # ʻOku paaki ʻe he CLI ʻa e ngaahi hala fokotuʻutuʻu ki stderr ʻi he fōtunga JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lau ʻa e ngaahi ngāue ʻoku ʻatā kotoa pea fakaʻilonga ʻa e ngaahi meʻa laka hake ʻi he ʻaho ʻe 30 kuo ʻosi.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tauhi ʻa e ngaahi fakangatangata leo

Manatu: 120/houa. Fetalanoaʻaki: 25/houa. Faʻu fakakātoa: 15/houa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # fakangatangata ʻa e leo
    err = json.loads(result.stderr)
    # ʻOku hangē `err["detail"]` ko: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ngaahi faleʻi

* Ngāueʻaki ʻa e `--profile <name>` kapau ʻoku pule ʻa hoʻo ʻākenga ʻi ha
  ngaahi ʻakauni Omi lahi. ʻOku ʻi he pōfilo takitaha hono fakamoʻoni pē mo hono
  API base.
* Ngāueʻaki ʻa e `--api-base http://localhost:8080` maʻa e sivi ʻi he backend
  fakalotofonua.
* Ngāueʻaki ʻa e `OMI_LOCAL_API_URL` mo `OMI_LOCAL_TOKEN` ke fetongi ʻa e ngaahi
  fokotuʻu API Desktop ʻo e pōfilo maʻa ha laka ʻe taha.
* Ngāueʻaki ʻa e `--verbose` maʻa e debugging — ʻoku ne loka ʻa e `METHOD path → status (Ns)` ki stderr
  ʻo ʻikai uesia ʻa e stdout, ko ia ʻoku kei ngāue ʻa e fōtunga JSON.
* Maʻa hono tuku ʻa e ʻū meʻa ki ha fetalanoaʻaki ʻaki e paipa, ngāueʻaki ʻa e `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
