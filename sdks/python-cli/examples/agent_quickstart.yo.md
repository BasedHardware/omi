# omi-cli fún àwọn ẹ̀rọ̀

> Àtọ̀ka tó ṣe é ṣe fún àwọn ètò tí LLM ń ṣàkóso (Claude Code, Cursor, àwọn bọ́tù rẹ).

## Bí kílíì sì ṣe rẹ̀ rọ́ra fún àwọn ẹ̀rọ̀

* **Òfin JSON tó rántì.** `--json` ń tọ́jú ìwé JSON tó tọ́ sí stdout àti
  ìwé JSON nìkan — kò sí ìwé ìlérí, kò sí àmì ìdúró. Àwọn àṣìṣe ń lọ sí
  stderr gẹ́gẹ́ bí `{"error": "...", "detail": "..."}`.
* **Kọ́dí ìpadà tó rántì.** `0` ó yẹ / `1` èlò / `2` ìdánwò / `3` sàávù / `4` ìdí
  ìṣẹ́ / `5` a kò rí. Àwọn ẹ̀rọ̀ lè dá àwọn yìí sílẹ̀ láì ka àṣìṣe nínú
  èdè àlàáfìà.
* **Kò sí ìbéèrè nínú kọ́ńtẹ́kstì headless.** Fi `--yes` (tàbí `-y`) kún àwọn
  àṣàǹtọ́jú; fi `--api-key` tàbí fi `OMI_API_KEY` sórí àyẹ̀wò àjọ̀ṣepọ̀.
* **Ìdánwò tó fúnnínú.** `429` àti `5xx` ń tún dánwò pẹ̀lú backoff
  kí wọ́n tó hàn.

## Ìdánwò (oókan, láti ọ̀wọ̀ ènìyàn)

Oníbàṣepọ̀ yóò mú kúlẹ̀ ìṣòwò́ API láti ìṣàkóso Omi wẹ́bù
(`https://app.omi.me` → Developer → API Keys) àti náà:

```bash
omi auth login                          # ìdánwò ìgbàsọ̀lẹ̀; kúlẹ̀ kò ń hàn nínú ìtàn shell
# tàbí
export OMI_API_KEY=omi_dev_...          # àkókò dípò, ìmúra fún àwọn kọntẹ́nà
```

## Àwọn ẹ̀jọ̀ márùn-ún tí àwọn ẹ̀rọ̀ ń ṣe jùlọ

### 1. Kà ìrònú

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Dá ìrònú kan mọ́

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Kà ìbánisúlọ̀wọ́

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Kà iṣẹ́ tó ṣí

```bash
omi action-item list --json --open
```

### 5. Fún iṣẹ́ kan ní pàtàkì

```bash
omi action-item complete --json a1b2c3d4
```

## API ìbílẹ̀ Desktop

Nígbà tí Omi Desktop fi API rẹ̀ hàn, àwọn ẹ̀rọ̀ lè bèèrè fún ìtàn ọ̀nà
àwòrán, àkójọ àbájáde, SQL àti iṣẹ́ láì lo API ìwọ̀n oòrùn dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# tàbí, fún ìpàdé dípò:
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

Parí tàbí yọ iṣẹ́ kuro nígbà tí olùṣàmúlò fẹ́ rẹ̀ ṣe pátápátá:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ń kọ àwòrán sínú
fáìlì àti kí ó tún JSON sórí stdout fún àwọn skrìpù. Àmì àwòrán tó wù
kọ́já ti `local search-screen` tàbí SQL lórí tábìlì `screenshots`. Tí Desktop
tún mú àṣìṣe àkànṣe bí `screenshot_pending`, `screenshot_file_missing`,
tàbí `screenshot_chunk_corrupted`, JSON mode fi `reason`, `hint`, àti
`screenshot_id` sílẹ̀ ní̀ stderr kí àwọn ẹ̀rọ̀ lè tún gbìyànjú pẹ̀lú àmì tó
jẹ́ tòótọ́ tàbí kí wọ́n sọ èyí tí ó ń dí ń dí. Ṣàṣọwò àwọn ìpèyà tí ó
yẹ pẹ̀lú `file PATH` kí wọ́n tó fi sí àwọn irinṣẹ́ ojú.

## Àpèjúwe: ọ̀nà ẹ̀rọ̀ Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Pe kílíì omi nínú JSON mode, ṣí àṣìṣe pẹ̀lú kọ́dí ìpadà tí kò jẹ́ o."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Kílíì ń kọ àṣìṣe àkànṣe sí stderr nínú JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Kà gbogbo àwọn iṣẹ́ tó ṣí àti fún tí ó kọjá ọjọ́ 30 sí pàtàkì.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Bí a ṣe ń dá ìdí ìṣẹ́ lọ́wọ́

Ìrónú: 120/wákàtí. Ìbánisúlọ̀wọ́: 25/wákàtí. Ìdá ọ̀pọ̀lọpọ̀: 15/wákàtí.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ìdí ìṣẹ́ ti dé
    err = json.loads(result.stderr)
    # err["detail"] dúró bí: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Àwọn ìmọ̀ràn

* Lo `--profile <orúkọ>` tíẹ́ bí ẹ̀rọ̀ rẹ ń ṣàkóso òfin Omi púpọ̀. Ìwọ̀n
  kọ̀ọ̀kan ní àwọn àkójọ àti àpótí API rẹ̀.
* Lo `--api-base http://localhost:8080` fún ìdánwò ìbílẹ̀ backend.
* Lo `OMI_LOCAL_API_URL` àti `OMI_LOCAL_TOKEN` láti yọ àwọn ìtọ́ka API Desktop
  kuro fún ìṣiṣẹ́ kan.
* Lo `--verbose` fún ìròyìn àṣìṣe — ó kọ `METHOD path → status (Ns)` sí stderr
  láì pa stdout, nígbẹ̀kẹ̀ JSON mode yóò tún ṣiṣẹ́.
* Láti fi kọ̀ọ̀kan sínú ìbánisúlọ̀wọ́ pẹ̀lú pipe, lo `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
