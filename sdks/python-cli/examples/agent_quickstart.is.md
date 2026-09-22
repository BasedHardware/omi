# omi-cli fyrir gervigreindarfulltrúa

> Hagnýt handbók fyrir umhverfi sem knúin eru af stórum málmódelum (Claude Code, Cursor, eigin vélmenni).

## Af hverju skipanalínan er sniðin að fulltrúum

* **Stöðugur JSON samningur.** `--json` rofinn skilar gildu JSON skjali á stdout og *eingöngu* JSON skjali — engin framvinduskilaboð, engir hleðsluhringir. Villur fara á stderr sem `{"error": "...", "detail": "..."}`.
* **Stöðugir lokakóðar (exit codes).** `0` í lagi / `1` notkunarvilla / `2` auðkenningarvilla / `3` netþjónsvilla / `4` beiðnatakmörkun náð / `5` fannst ekki. Fulltrúar geta tekið ákvarðanir út frá þessum kóðum án þess að þurfa að þátta skilaboð á náttúrulegu máli.
* **Engar gagnvirkar fyrirspurnir í bakgrunnsstillingu.** Senda skal `--yes` (eða `-y`) með eyðingarskipunum; senda skal `--api-key` eða stilla umhverfisbreytuna `OMI_API_KEY` til að sleppa gagnvirkri innskráningu.
* **Sveigjanleg endurtekningarhegðun.** Villukóðar `429` og `5xx` eru sjálfkrafa reyndir aftur með stigvaxandi töf (backoff) áður en villan er birt.

## Auðkenning (einu sinni, framkvæmd af manneskju)

Notandinn sækir API-lykil þróunaraðila úr Omi vefforritinu
(`https://app.omi.me` → Developer → API Keys) og keyrir annað hvort:

```bash
omi auth login                          # gagnvirkt límt; lykill geymist ekki í skipanaferli skeljar
# eða
export OMI_API_KEY=omi_dev_...          # tímabundið, hentar vel í gáma (containers)
```

## Fimm algengustu aðgerðir fulltrúa

### 1. Lesa minningar (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Búa til minningu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lesa samtöl

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lesa opnar verkbeiðnir (action items)

```bash
omi action-item list --json --open
```

### 5. Merkja verkefni sem lokið

```bash
omi action-item complete --json a1b2c3d4
```

## Staðbundið Desktop API (Local Desktop API)

Þegar Omi Desktop virkjar staðbundið API sitt geta fulltrúar skoðað skjásögu tækisins, samantektir, SQL og verkefni án þess að nota skýja-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eða fyrir tímabundnar setur:
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

Ljúka eða eyða verkefnum eingöngu þegar notandinn óskar þess sérstaklega:

```bash
omi --json local task complete task_1
```
