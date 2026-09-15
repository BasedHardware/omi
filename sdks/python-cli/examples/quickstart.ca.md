# omi-cli Guia d'inici ràpid (Catalan Quickstart)

> Guia pràctica per utilitzar Omi directament des del terminal — pensada per a desenvolupadors i agents d'intel·ligència artificial autònoms.

`omi-cli` és la interfície de línia d'ordres (CLI) oficial per a l'API de desenvolupadors d'[Omi](https://omi.me). Ofereix accés estructurat als 4 recursos essencials d'Omi: memòries (*memories*), converses (*conversations*), tasques d'acció (*action items*) i objectius (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentació oficial:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Codi font:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instal·lació

Per tal de garantir un entorn aïllat i evitar conflictes amb les dependències de Python del sistema, es recomana fermament utilitzar `pipx`:

```bash
# Mètode recomanat: instal·lació aïllada mitjançant pipx
pipx install omi-cli

# Instal·lació alternativa amb pip (per exemple, dins d'un entorn virtual)
pip install omi-cli
```

> **Aclariment fonamental: Nom del paquet enfront de nom de l'ordre**
> * El nom oficial del paquet a PyPI és **`omi-cli`** (el paquet anomenat `omi` és un projecte diferent i desvinculat).
> * L'ordre que s'executa a la consola és directament: **`omi`**.

Comproveu que la instal·lació s'ha completat correctament mostrant la versió i el menú d'ajuda:

```bash
omi --version
omi --help
```

---

## 2. Autenticació (Authentication)

`omi-cli` admet dos mètodes principals de verificació d'identitat:

| Mètode | Ús idoni | Ordre d'exemple |
| :--- | :--- | :--- |
| **Clau d'API de desenvolupador (`omi_dev_*`)** | Scripts d'automatització, fluxos CI/CD, servidors, agents d'IA | `omi auth login --api-key ...` o `OMI_API_KEY` |
| **Inici de sessió OAuth amb navegador** | Desenvolupament local en estacions de treball personals | `omi auth login --browser` (Google) / `--provider apple` |

### Inici de sessió interactiu

Si executeu l'ordre sense paràmetres addicionals, s'obre un menú interactiu:

```bash
omi auth login
# 1) Browser — Inici de sessió amb navegador web (Google o Apple)
# 2) API key — Enganxar una clau de desenvolupador obtinguda a app.omi.me
```

### Inici de sessió mitjançant el navegador web

```bash
# Inici de sessió estàndard amb compte de Google
omi auth login --browser

# Inici de sessió alternatiu amb compte d'Apple
omi auth login --browser --provider apple
```

### Inici de sessió amb clau d'API de desenvolupador

Genereu la vostra clau d'API al tauler de control d'[app.omi.me](https://app.omi.me) a la secció **Developer → API Keys**:

```bash
# Desar la clau al perfil local actiu
omi auth login --api-key omi_dev_la_vostra_clau_aqui

# O bé establir-la com a variable d'entorn (recomanat per a contenidors Docker i entorns CI/CD):
export OMI_API_KEY="omi_dev_la_vostra_clau_aqui"
```

### Comprovació de l'estat d'autenticació

* `omi auth status`: Mostra el perfil actiu i l'identificador emmascarat a partir de la configuració local (funciona sense connexió).
* `omi auth whoami`: Fa una petició de xarxa al servidor d'Omi per comprovar la validesa real de la sessió.

```bash
omi auth status
omi auth whoami
```

### Tancament de sessió (Logout)

Per esborrar les credencials desades localment:

```bash
omi auth logout
# Si heu utilitzat la variable d'entorn OMI_API_KEY, elimineu-la de la sessió:
unset OMI_API_KEY
```

> **Nota de seguretat:** La configuració es desa al fitxer `~/.omi/config.toml`. En entorns Unix, és aconsellable restringir els permisos: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Ordres principals

### Memòries (Memories)

Registre i consulta de fets, observacions i context durador:

```bash
# Llistat de memòries emmagatzemades
omi memory list

# Creació d'una nova memòria
omi memory create "L'usuari prefereix respostes tècniques concises amb exemples en Python" --category work

# Consulta d'una memòria concreta per identificador
omi memory get <ID_MEMÒRIA>
```

### Converses (Conversations)

Enregistraments d'àudio i transcripcions generades pels dispositius Omi:

```bash
# Llistat de les 5 darreres converses
omi conversation list --limit 5

# Consulta d'una conversa amb la transcripció completa
omi conversation get <ID_CONVERSA> --include-transcript
```

### Tasques d'acció (Action Items)

Tasques pendents detectades automàticament durant les converses:

```bash
# Llistat de tasques d'acció obertes
omi action-item list --open

# Marcar una tasca com a completada
omi action-item complete <ID_TASCA>
```

### Objectius (Goals)

Seguiment d'objectius a llarg termini i progrés acumulat:

```bash
# Llistat dels objectius actius
omi goal list

# Creació d'un nou objectiu numèric (el títol es passa com a argument posicional)
omi goal create "Consum diari d'aigua" --type numeric --target 2500 --unit "ml"
```

---

## 4. Automatització estructurada i sortida JSON (`--json`)

`omi-cli` s'integra de forma nativa en scripts i agents d'intel·ligència artificial. El modificador global `--json` garanteix una sortida neta en format JSON per processar-la amb eines com `jq`:

```bash
# Llistar memòries en format JSON i filtrar amb jq
omi --json memory list | jq '.[] | {id, content, category}'

# Obtenir els títols de les darreres 5 converses
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Consultar les tasques obertes
omi --json action-item list --open | jq '.'
```

> **Regla de sintaxi imprescindible:**
> L'opció `--json` és un **modificador global**, per la qual cosa s'ha d'escriure sempre **abans** de la subordre:
> * Correcte: `omi --json memory list`
> * Incorrecte: `omi memory list --json`

### Paginació i exportació de dades

Quan treballeu amb conjunts de dades amplis, utilitzeu els paràmetres `--limit` i `--offset`:

```bash
# Paginació de resultats
omi --json memory list --limit 25 --offset 0 > memories-pagina-1.json
omi --json memory list --limit 25 --offset 25 > memories-pagina-2.json
```

La redirecció a un fitxer crea o sobreescriu el fitxer local. Comproveu sempre el codi de sortida de l'ordre abans de processar les dades. Els missatges d'error es canalitzen pel canal d'errors estàndard (`stderr`), per la qual cosa un fitxer buit no garanteix l'absència de dades. Els fitxers exportats poden contenir informació privada — protegiu-los segons les vostres polítiques de seguretat.

---

## 5. Codis de sortida (Exit Codes Contract)

`omi-cli` implementa un contracte de codis de sortida precís per a un control d'errors fiable en scripts i entorns CI/CD (conforme a `omi_cli/errors.py`):

| Codi | Identificador | Significat i descripció |
| :---: | :--- | :--- |
| `0` | **Èxit (`EXIT_OK`)** | L'ordre s'ha executat satisfactòriament sense errors. |
| `1` | **Error d'ús / Validació (`EXIT_USAGE`)** | Valors d'arguments incorrectes o error de validació a nivell d'aplicació (per exemple, especificar simultàniament `--browser` i `--api-key`). |
| `2` | **Error d'autenticació (`EXIT_AUTH`) / Parser** | Credencials absents, clau caducada o permisos insuficients. Els errors de sintaxi del parser Click (opcions desconegudes/arguments absents) també retornen el codi 2. |
| `3` | **Error de servidor o xarxa (`EXIT_SERVER`)** | Resposta HTTP 5xx del servidor d'Omi o interrupció del canal de xarxa. |
| `4` | **Límit de peticions superat (`EXIT_RATE_LIMITED`)** | Resposta HTTP 429 — massa peticions enviades en un període breu de temps. |
| `5` | **Recurs no trobat (`EXIT_NOT_FOUND`)** | Resposta HTTP 404 — el recurs sol·licitat no existeix. |

---

## 6. Exemples per a diferents entorns de terminal

### Bash / Zsh (Linux i macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "S'han obtingut correctament $(jq 'length' /tmp/memories.json) memòries."
else
    code=$?
    echo "Error en obtenir les memòries (codi de sortida: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "L'ordre ha fallat amb el codi de sortida $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Dades desades correctament."
```

### Símbol del sistema de Windows (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo S'ha produït un error amb codi %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Operació completada satisfactòriament.
```

---

## 7. Gestió de perfils i entorn de proves (Staging)

L'opció `--profile` permet gestionar múltiples configuracions independents de manera simultània. Per a entorns de prova o posada en escena, utilitzeu el paràmetre `--api-base`:

```bash
# Inici de sessió en un perfil de proves (staging)
omi --profile staging --api-base https://api.staging.omi.me auth login --api-key omi_dev_staging_clau

# Execució d'ordres sota el perfil de proves
omi --profile staging memory list
```

---

## 8. Integració amb l'API local de l'escriptori (Local Desktop API)

Si l'aplicació d'escriptori Omi està en execució al mateix equip, podeu consultar directament el servidor local sense enviar dades al núvol. Abans d'executar ordres locals, configureu l'adreça del node i el testimoni d'accés:

```bash
# Configuració de l'adreça local (port per defecte 47778) i del testimoni:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="el_vostre_token_local"

# Comprovació de l'estat del servei local
omi local status

# Cerca en l'historial de pantalles per consulta i aplicació
omi local search-screen "reunió de projecte" --days 1 --app "Slack"
```

---

## 9. Bones pràctiques i seguretat

1. **Ubicació de la bandera `--json`:** Cal situar-la sempre abans de la subordre (`omi --json memory list`).
2. **Control dels codis de sortida:** En entorns automatitzats, comproveu i tracteu sempre els codis d'error de l'1 al 5.
3. **Custòdia de credencials:** No incorporeu mai claus d'API en dipòsits de codi públics. En entorns de producció i CI/CD, utilitzeu sempre la variable d'entorn `OMI_API_KEY`.
