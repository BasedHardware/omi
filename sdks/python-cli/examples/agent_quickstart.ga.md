# omi-cli do ghníomhairí

> Treoir phraiticiúil do thimpeallachtaí bunaithe ar LLM (Claude Code, Cursor, do róbait féin).

## Cén fáth a bhfuil an CLI oiriúnach do ghníomhairí

* **Conradh cobhsaí JSON.** Eiseoidh an bratach `--json` cáipéis bhailí JSON chuig stdout agus *cáipéis JSON amháin* — gan teachtaireachtaí dul chun cinn, gan guairneáin lódála. Téann earráidí chuig stderr mar `{"error": "...", "detail": "..."}`.
* **Códanna fágála cobhsaí.** `0` ceart / `1` earráid úsáide / `2` earráid fhíordheimhnithe / `3` earráid freastalaí / `4` teorainn ráta sáraithe / `5` gan aimsiú. Is féidir le gníomhairí cinntí a dhéanamh bunaithe ar na códanna seo gan teachtaireachtaí teanga nádúrtha a pharsáil.
* **Gan leideanna idirghníomhacha i mód gan ceann (headless).** Cuir `--yes` (nó `-y`) le horduithe millteacha; cuir `--api-key` nó socraigh an athróg thimpeallachta `OMI_API_KEY` chun logáil isteach idirghníomhach a sheachaint.
* **Iompraíocht athiarrachta maithiúnach.** Déantar iarracht arís go huathoibríoch ar chóid earráide `429` agus `5xx` le moill fhorásach (backoff) sula dtaispeántar earráid.

## Fíordheimhniú (aon uair amháin, déanta ag duine)

Faigheann an t-úsáideoir eochair API forbróra ón bhfeidhmchlár gréasáin Omi
(`https://app.omi.me` → Developer → API Keys) agus ritheann ceann amháin díobh seo a leanas:

```bash
omi auth login                          # greamú idirghníomhach; ní shábháiltear an eochair i stair na blaaoisce
# nó
export OMI_API_KEY=omi_dev_...          # sealadach, oiriúnach do choimeádáin (containers)
```

## Na cúig rud is mó a dhéanann gníomhairí

### 1. Cuimhní a léamh (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cuimhne a chruthú

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Comhráite a léamh

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Tascanna oscailte a léamh (action items)

```bash
omi action-item list --json --open
```

### 5. Tasc a mharcáil mar chomhlánaithe

```bash
omi action-item complete --json a1b2c3d4
```

## API Deisce Áitiúil (Local Desktop API)

Nuair a chuireann Omi Desktop a API áitiúil ar fáil, is féidir le gníomhairí stair scáileáin, achoimrí, SQL agus tascanna ar an ngléas a cheistiú gan an scamall API a úsáid:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# nó do sheisiúin shealadacha:
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

Ná déan tascanna a chur i gcrích nó a scriosadh ach amháin nuair a iarrann an t-úsáideoir go sainráite é:

```bash
omi --json local task complete task_1
```
