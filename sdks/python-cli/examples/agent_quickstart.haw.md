# omi-cli no nā ʻelele

> Alakaʻi hana no nā mea hana i alakaʻi ʻia e LLM (Claude Code, Cursor, kāu mau lopako ponoʻī).

## No ke aha he aloha ka CLI i nā ʻelele

* **Kikowaena JSON paʻa.** Hoʻopuka ʻo `--json` i kahi palapala JSON kūpono i
  stdout — *ʻo ia wale nō* — ʻaʻohe memo holomua, ʻaʻohe wili. Hele nā hewa i
  stderr me ke ʻano `{"error": "...", "detail": "..."}`.
* **Nā helu puka paʻa.** `0` maikaʻi / `1` hoʻohana / `2` hōʻoia / `3` kikowaena
  / `4` palena wikiwiki / `5` ʻaʻole i loaʻa. Hiki i nā ʻelele ke koho ma kēia
  mau helu me ka ʻole e ʻohi i nā hewa ʻōlelo kanaka.
* **ʻAʻohe nīnau hoʻopili i nā wahi headless.** Hāʻawi iā `--yes` (a i ʻole `-y`)
  i nā kauoha luku; hāʻawi iā `--api-key` a i ʻole e hoʻonoho iā `OMI_API_KEY`
  e kāpae i ke komo hoʻopili.
* **Hana hoʻāʻo hou ahonui.** Hoʻāʻo hou ʻia ʻo `429` a me `5xx` me ka hoʻi ʻana
  i hope ma mua o ka hōʻike ʻia.

## Hōʻoia (hoʻokahi manawa, na ke kanaka)

Loaʻa i ka mea hoʻohana kahi kī API dev mai ka polokalamu pūnaewele ʻo Omi
(`https://app.omi.me` → Developer → API Keys) a koho pēlā:

```bash
omi auth login                          # hoʻopili lima; ʻaʻole i loko o ka mōʻaukala shell ke kī
# a i ʻole
export OMI_API_KEY=omi_dev_...          # pōkole, kūpono no ka pahu
```

## Nā hana ʻelima a nā ʻelele e hana pinepine ai

### 1. Heluhelu i nā hoʻomanaʻo

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Hana i kahi hoʻomanaʻo

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Heluhelu i nā kamaʻilio

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Heluhelu i nā hana hāmama

```bash
omi action-item list --json --open
```

### 5. Hoʻopau i kahi hana

```bash
omi action-item complete --json a1b2c3d4
```

## API Papapihi Kūloko

Ke hōʻike ʻo Omi Desktop i kāna API kūloko, hiki i nā ʻelele ke nīnau i ka
mōʻaukala pale ma ka pā hana, nā hōʻuluʻulu, SQL, a me nā hana me ka hoʻohana
ʻole i ka API dev o ke ao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# a i ʻole, no nā wā pōkole:
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

E hoʻopau a holoi paha i nā hana wale nō ke noi maopopo ke kanaka:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Kākau ʻo `omi local screenshot SCREENSHOT_ID --output PATH` i ke kiʻi pale i ka
diski a paʻi mau i ka JSON i stdout no nā palapala. Loaʻa ka ID kiʻi pale mai
`local search-screen` a i ʻole SQL ma luna o ka papaʻaina `screenshots`. Inā
hoʻihoʻi ʻo Desktop i kahi hemahema i kūkulu ʻia e like me `screenshot_pending`,
`screenshot_file_missing`, a i ʻole `screenshot_chunk_corrupted`, mālama ke ʻano
JSON i nā kahua `reason`, `hint`, a me `screenshot_id` ma stderr i hiki i nā
ʻelele ke hoʻāʻo hou me kahi ID kahiko a hōʻike paha i ka pilikia pololei.
Hōʻoia i nā pukana kūleʻa me `file PATH` ma mua o ka hāʻawi ʻana i nā mea hana
ʻike.

## Laʻana hana: pōʻaiapuni ʻelele Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """E hoʻohana i ka CLI omi ma ke ʻano JSON, e hoʻāla i ka hewa ke ʻole he kūleʻa ka helu puka."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Paʻi ka CLI i nā hemahema kūkulu i stderr ma ke ʻano JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Heluhelu i nā hana hāmama a pau a hōʻailona i nā mea ʻoi aku i 30 lā ua paʻa.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ka mālama ʻana i nā palena wikiwiki

Hoʻomanaʻo: 120/hola. Kamaʻilio: 25/hola. Hana pūʻulu: 15/hola.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ua pā i ka palena wikiwiki
    err = json.loads(result.stderr)
    # like err["detail"] me: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nā ʻōlelo aʻoaʻo

* E hoʻohana iā `--profile <name>` inā lawelawe kāu ʻelele i nā moʻokāki Omi
  he nui. Loaʻa i kēlā me kēia ʻaoʻao kona mau hōʻoia ponoʻī a me kona API base.
* E hoʻohana iā `--api-base http://localhost:8080` no ka hoʻāʻo ʻana i ke kua
  kūloko.
* E hoʻohana iā `OMI_LOCAL_API_URL` a me `OMI_LOCAL_TOKEN` e hoʻololi i nā
  hoʻonohonoho API Desktop o ka ʻaoʻao no ka holo hoʻokahi.
* E hoʻohana iā `--verbose` no ka hoʻopau ʻana — kākau ia i `METHOD path → status (Ns)` i stderr
  me ka pā ʻole i stdout, no laila paʻa mau ke ʻano JSON.
* No ka hoʻokomo ʻana i ka ʻike i loko o kahi kamaʻilio, e hoʻohana iā `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
