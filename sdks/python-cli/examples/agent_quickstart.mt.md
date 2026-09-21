# omi-cli għall-aġenti

> Gwida prattika għal oqfsa mmexxija minn LLM (Claude Code, Cursor, il-bots personali tiegħek).

## Għaliex is-CLI huwa faċli għall-aġenti

* **Kuntratt JSON stabbli.** `--json` joħroġ dokument JSON validu f'stdout u
  *biss* dokument JSON — l-ebda messaġġi ta' progress, l-ebda spinners. L-iżbalji jmorru
  f'stderr bħala `{"error": "...", "detail": "..."}`.
* **Kodiċijiet tal-ħruġ stabbli.** `0` kollox sew / `1` użu / `2` awtentikazzjoni / `3` server / `4` limitu
  ta' talbiet / `5` mhux misjub. L-aġenti jistgħu jinferqu abbażi ta' dawn mingħajr ma janalizzaw
  żbalji f'lingwa naturali.
* **L-ebda mistoqsijiet interattivi f'kuntesti mingħajr skrin (headless).** Għaddi `--yes` (jew `-y`) lil
  kmandi distruttivi; għaddi `--api-key` jew issettja `OMI_API_KEY` biex taqbeż
  id-dħul interattiv.
* **Imġiba ta' prova mill-ġdid li taħfer.** `429` u `5xx` jerġgħu jiġu ppruvati b'dewmien
  esponenzjali qabel ma jitfaċċaw.

## Awtentikazzjoni (darba waħda, mill-bniedem)

L-utent jikseb ċavetta tal-API tal-iżviluppatur mill-app tal-web ta' Omi
(`https://app.omi.me` → Developer → API Keys) u jew:

```bash
omi auth login                          # pejst interattiv; iċ-ċavetta mhix fl-istorja tat-terminal
# jew
export OMI_API_KEY=omi_dev_...          # temporanju, adattat għall-containers
```

## Il-ħames affarijiet li l-aġenti jagħmlu l-aktar

### 1. Aqra l-memorji

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Oħloq memorja

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Aqra l-konversazzjonijiet

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Aqra l-oġġetti ta' azzjoni miftuħa

```bash
omi action-item list --json --open
```

### 5. Immarka oġġett ta' azzjoni bħala lest

```bash
omi action-item complete --json a1b2c3d4
```

## API Lokali tad-Desktop

Meta Omi Desktop jesponi l-API lokali tiegħu, l-aġenti jistgħu jistaqsu l-istorja
tal-iskrin fuq l-apparat, rikapitulazzjonijiet, SQL, u kompiti mingħajr ma jużaw l-API tal-iżviluppatur tal-cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# jew, għal sessjonijiet temporanji:
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

Ikkonkludi jew ħassar il-kompiti biss meta l-utent jitlob b'mod ċar:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` jikteb il-qbid tal-iskrin fuq
id-diska u xorta joħroġ JSON f'stdout għall-iskripts. L-ID tal-screenshot normalment
jiġi minn `local search-screen` jew SQL fuq it-tabella `screenshots`. Jekk Desktop
jirritorna falliment strutturat bħal `screenshot_pending`, `screenshot_file_missing`,
jew `screenshot_chunk_corrupted`, il-modalità JSON tippreserva l-oqsma `reason`, `hint`, u
`screenshot_id` fuq stderr biex l-aġenti jkunu jistgħu jerġgħu jippruvaw ID aktar qadima jew jirrappurtaw
l-ostaklu eżatt. Ivvalida l-outputs b'suċċess b'`file PATH` qabel ma tgħaddihom
lil għodod tal-viżjoni.

## Eżempju prattiku: linja ta' aġent f'Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoka s-CLI omi fil-modalità JSON, u qajjem eċċezzjoni fuq kodiċijiet ta' ħruġ mhux ta' suċċess."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Is-CLI jistampa żbalji strutturati f'stderr fil-modalità JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Aqra l-oġġetti kollha ta' azzjoni miftuħa u mmarka kwalunkwe ħaġa aktar antika minn 30 jum bħala lesta.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Immaniġġjar tal-limiti ta' talbiet

Memorji: 120/siegħa. Konversazzjonijiet: 25/siegħa. Ħolqien f'lottijiet: 15/siegħa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitu ta' talbiet milħuq
    err = json.loads(result.stderr)
    # err["detail"] jidher bħal: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suġġerimenti

* Uża `--profile <isem>` jekk l-aġent tiegħek jimmaniġġja diversi kontijiet ta' Omi. Kull
  profil għandu l-kredenzjali u l-bażi tal-API tiegħu stess.
* Uża `--api-base http://localhost:8080` għall-ittestjar tal-backend lokali.
* Uża `OMI_LOCAL_API_URL` u `OMI_LOCAL_TOKEN` biex tegħleb is-settings tal-API tad-Desktop
  lokali għall-profil għal darba waħda.
* Uża `--verbose` għad-debugging — jirreġistra `METHOD path → status (Ns)` f'stderr
  mingħajr ma jaffettwa stdout, u b'hekk il-modalità JSON tibqa' valida.
* Biex tibgħat kontenut f'konversazzjoni, uża `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
