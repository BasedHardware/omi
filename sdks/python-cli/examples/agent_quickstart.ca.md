# omi-cli per a agents

> Guia pràctica per a entorns basats en models LLM (Claude Code, Cursor, els vostres propis bots).

## Per què la CLI és adequada per a agents

* **Contracte JSON estable.** La bandera `--json` emet un document JSON vàlid a stdout i *únicament* un document JSON — sense missatges de progrés, sense indicadors de càrrega. Els errors van a stderr com `{"error": "...", "detail": "..."}`.
* **Codis de sortida estables (exit codes).** `0` correcte / `1` error d'ús / `2` error d'autenticació / `3` error de servidor / `4` límit de peticions superat / `5` no trobat. Els agents poden prendre decisions a partir d'aquests codis sense analitzar missatges en llenguatge natural.
* **Sense preguntes interactives en mode headless.** Passeu `--yes` (o `-y`) per a ordres destructives; passeu `--api-key` o definiu la variable d'entorn `OMI_API_KEY` per ometre l'inici de sessió interactiu.
* **Comportament de reintent flexible.** Els codis d'error `429` i `5xx` es reintenten automàticament amb un retard exponencial (backoff) abans de mostrar l'error.

## Autenticació (única vegada, realitzada per una persona)

L'usuari obté una clau API de desenvolupador des de l'aplicació web d'Omi
(`https://app.omi.me` → Developer → API Keys) i executa una de les següents opcions:

```bash
omi auth login                          # enganxament interactiu; la clau no es desa a l'historial del terminal
# o bé
export OMI_API_KEY=omi_dev_...          # efímer, ideal per a contenidors
```

## Les cinc accions més freqüents dels agents

### 1. Llegir records (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear un record

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Llegir converses

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Llegir tasques pendents (action items)

```bash
omi action-item list --json --open
```

### 5. Marcar una tasca com a completada

```bash
omi action-item complete --json a1b2c3d4
```

## API d'escriptori local (Local Desktop API)

Quan Omi Desktop habilita la seva API local, els agents poden consultar l'historial de pantalla del dispositiu, resums, SQL i tasques sense utilitzar l'API al núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o bé per a sessions efímeres:
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

Completeu o elimineu tasques només quan l'usuari ho demani explícitament:

```bash
omi --json local task complete task_1
```
