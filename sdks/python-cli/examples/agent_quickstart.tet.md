# omi-cli ba ajente sira

> Matadalan pratiku ba harness ne'ebé LLM dadaun (Claude Code, Cursor, o nia bot rasik).

## Tansá CLI di'ak ba ajente sira

* **Kontratu JSON estável.** `--json` halo dokumentu JSON válidu ba stdout no
  *de'it* dokumentu JSON — la iha mensajen progresu, la iha spinner. Erru sira ba
  stderr hanesan `{"error": "...", "detail": "..."}`.
* **Kódigu saída estável.** `0` di'ak / `1` uza / `2` auth / `3` servidór /
  `4` limite lalais / `5` la hetan. Ajente sira bele halo desizaun iha sira ne'e
  la'analiza erru iha lian naturál.
* **Laiha prompt interativu iha kontestu headless.** Fó `--yes` (ka `-y`) ba
  komandu destruktivu; fó `--api-key` ka estabelese `OMI_API_KEY` hodi liu
  login interativu.
* **Comportamentu retry ne'ebé laran.** `429` no `5xx` hetan tentativu ho backoff
  molok sai.

## Auth (dala ida, husi ema)

Utilizadór hetan dev API key husi aplikasaun web Omi
(`https://app.omi.me` → Developer → API Keys) no ou:

```bash
omi auth login                          # kola interativu; key la hela iha istória shell
# ou
export OMI_API_KEY=omi_dev_...          # temporáriu, di'ak ba konteiner
```

## Buat lima ne'ebé ajente sira halo liu

### 1. Lee memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kria memoria ida

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lee koñversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lee pontu asaun ne'ebé nakloke

```bash
omi action-item list --json --open
```

### 5. Marka pontu asaun hanesan remata

```bash
omi action-item complete --json a1b2c3d4
```

## API lokál Desktop nian

Bainhira Omi Desktop expõe nia API lokál, ajente sira bele pergunta istória
ekra dispositivu, recaps, SQL, no servisu la uza API dev iha núvem:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou, ba sesuáun temporáriu:
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

Remata ka hamenus servisu de'it bainhira utilizadór husu klaru:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` hakerek screenshot ba disk no
sei imprime JSON ba stdout ba script sira. ID screenshot normalmente mai husi
`local search-screen` ka SQL iha tabela `screenshots`. Se Desktop fó erru
estruturadu hanesan `screenshot_pending`, `screenshot_file_missing`, ka
`screenshot_chunk_corrupted`, modu JSON konserva kampu `reason`, `hint`, no
`screenshot_id` iha stderr hodi ajente sira bele tentativu ho ID tuan ka reporta
blokeiu ezatu. Valida rezultadu di'ak ho `file PATH` molok fó ba ferramenta vizaun.

## Ezemplu serbisu: bukle ajente Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Jere limite lalais

Memorias: 120/óra. Koñversas: 25/óra. Kriasuáun lote: 15/óra.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Konsellu

* Uza `--profile <name>` se o nia ajente jere konta Omi barak. Kada perfil iha
  nia kredensiál no base API rasik.
* Uza `--api-base http://localhost:8080` ba teste backend lokál.
* Uza `OMI_LOCAL_API_URL` no `OMI_LOCAL_TOKEN` hodi substitui perfil nia
  konfigurasaun API lokál Desktop ba ejekusaun ida.
* Uza `--verbose` ba depurasaun — rejista `METHOD path → status (Ns)` ba stderr
  la afeta stdout, entaun modu JSON sei válidu.
* Ba pipe konteúdu ba koñversa, uza `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
