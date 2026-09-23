# omi-cli ba ajente sira

> Guia prátika ba instrumentu sira ne'ebé orienta husi LLM (Claude Code, Cursor, ó-nia bot rasik).

## Tanbasá CLI ne'e fasil ba ajente sira

* **Kontratu JSON estavel.** `--json` fo sai dokumentu JSON ida ne'ebé válidu ba
  stdout — *dokumentu JSON de'it* — la iha mensajen progresu, la iha spinner.
  Erru sira bá ba stderr ho forma `{"error": "...", "detail": "..."}`.
* **Kódigu sáida estavel.** `0` diak / `1` uzu / `2` autentikasaun / `3` servidór
  / `4` limitadu taxa / `5` la hetan. Ajente sira bele deside bazeia ba sira-ne'e
  la'ós atu analiza erru lingua naturál.
* **La iha pergunta interativu iha kontextu headless.** Fó `--yes` (ka `-y`) ba
  komandu destruktivu sira; fó `--api-key` ka define `OMI_API_KEY` atu salta
  login interativu.
* **Komportamentu repete ne'ebé perdoa.** `429` no `5xx` repete ho backoff
  antes atu mosu.

## Autentikasaun (dala ida, husi ema)

Uza-na'in hetan xave API dev husi aplikasaun web Omi
(`https://app.omi.me` → Developer → API Keys) no hili ida:

```bash
omi auth login                          # kolante interativu; xave la tama ba istória shell
# ka
export OMI_API_KEY=omi_dev_...          # temporáriu, diak ba kontainer
```

## Buat lima ne'ebé ajente sira halo barak liu

### 1. Lee memória sira

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kria memória ida

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lee konversasaun sira

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lee item asaun ne'ebé nakloke

```bash
omi action-item list --json --open
```

### 5. Marka item asaun ida konkluidu

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lokál

Bainhira Omi Desktop hatudu nia API lokál, ajente sira bele husu istória ekrán
iha dispositivu, rekapitulasaun, SQL, no tarefa sira la uza API dev iha nuvem:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ka, ba sesaun temporáriu sira:
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

Konklui ka hamoos tarefa sira de'it bainhira uza-na'in husu klaru:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` hakerek screenshot ba disku
no sei imprime JSON ba stdout ba skript sira. ID screenshot normalmente mai husi
`local search-screen` ka SQL iha tabela `screenshots`. Se Desktop fila fali
falla estruturadu hanesan `screenshot_pending`, `screenshot_file_missing`, ka
`screenshot_chunk_corrupted`, modu JSON preserva kampu `reason`, `hint`, no
`screenshot_id` iha stderr atu ajente sira bele repete ho ID tuan ka reporta
blokeador exatu. Valida rezultadu susesu ho `file PATH` antes atu fó ba
instrumentu vizaun.

## Ezemplu servisu: loop ajente Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoka CLI omi iha modu JSON, hamosu erru bainhira kódigu sáida la susesu."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI imprime erru estruturadu ba stderr iha modu JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lee item asaun nakloke hotu no marka sira ne'ebé liu loron 30 ona konkluidu.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Halo maneja limitasaun taxa

Memória: 120/ora. Konversasaun: 25/ora. Kria lote: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitadu taxa
    err = json.loads(result.stderr)
    # err["detail"] hanesan: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Konsellu sira

* Uza `--profile <name>` se ó-nia ajente jere konta Omi barak. Kada prufil iha
  nia kredensial rasik no nia API base.
* Uza `--api-base http://localhost:8080` ba teste backend lokál.
* Uza `OMI_LOCAL_API_URL` no `OMI_LOCAL_TOKEN` atu troka konfigurasaun API
  Desktop husi prufil ba execusaun ida.
* Uza `--verbose` ba debugging — hakerek `METHOD path → status (Ns)` ba stderr
  la afeta stdout, nune'e modu JSON sei válidu.
* Atu pasa konteúdu ba konversasaun, uza `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
