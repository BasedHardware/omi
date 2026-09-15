# omi-cli — guia ràpida en català

> Guia pràctica per treballar amb Omi des del terminal. Serveix tant per a una persona com per a un agent d'IA.

`omi-cli` és la interfície de línia d'ordres oficial de l'API per a desenvolupadors d'[Omi](https://omi.me).
Ofereix un accés ràpid i scriptable a les quatre entitats principals d'Omi:
memòries (memories), converses (conversations), tasques (action items) i objectius (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentació:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Codi font:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instal·lació

La manera recomanada és `pipx`: instal·la l'eina en un entorn aïllat,
així que les seves dependències no entren en conflicte amb els teus projectes.

```bash
# recomanat: instal·lació amb pipx
pipx install omi-cli

# o amb pip
pip install omi-cli
```

> **Important: el nom del paquet i el nom de l'ordre són diferents.**
> * El paquet que s'instal·la és **`omi-cli`** (el paquet independent `omi` és un projecte diferent, sense relació).
> * Un cop instal·lat, l'ordre que s'executa és **`omi`**.

Comproveu que la instal·lació ha funcionat:

```bash
omi --version
omi --help
```

---

## 2. Autenticació

`omi-cli` admet dues maneres d'iniciar sessió.

| Manera | Quan convé | Ordre |
| :--- | :--- | :--- |
| **Clau de desenvolupador (`omi_dev_*`)** | CI/CD, scripts, agents d'IA | `omi auth login --api-key ...` o variable d'entorn |
| **Inici de sessió al navegador (Google/Apple)** | Treballar al teu ordinador | `omi auth login --browser` |

### Inici de sessió interactiu

Sense cap flag, l'ordre mateix us preguntarà com voleu entrar:

```bash
omi auth login
# 1) Browser — entrada amb Google o Apple (còmode per a una persona)
# 2) API key — enganxar la clau de desenvolupador d'app.omi.me (còmode per a agents i CI)
```

Si trieu la clau, l'entrada queda emmascarada, de manera que la clau no queda a l'historial del terminal.

### Directament amb el navegador

```bash
omi auth login --browser
```

### Amb la clau de desenvolupador

La clau es genera a [app.omi.me](https://app.omi.me), a la secció **Developer → API Keys**.

```bash
# desar la clau a la configuració
omi auth login --api-key omi_dev_...

# o passar-la per l'entorn — preferible per a CI/CD i contenidors
export OMI_API_KEY=omi_dev_...
```

La variable `OMI_API_KEY` s'utilitza quan el perfil actiu no té cap clau desada,
de manera que en un contenidor no cal escriure res al disc. Si el perfil ja té
una clau desada, aquesta té prioritat sobre la variable d'entorn.

### Comprovació de la sessió

Dues ordres responen a preguntes diferents i no s'han de confondre:

* `omi auth status` — què hi ha desat **en local**: perfil, clau emmascarada, vigència.
  Funciona sense xarxa.
* `omi auth whoami` — consulta **al servidor d'Omi**: comprova que la clau
  realment s'accepta. Necessita xarxa.

```bash
omi auth status    # comprovació local, fora de línia
omi auth whoami    # comprovació al servidor
```

Renovar una sessió OAuth a punt de caducar sense tornar a iniciar sessió — només per a l'inici de sessió al navegador (OAuth). Per a claus `omi_dev_*` aquesta ordre no renova res; gira la clau a l'aplicació web a `Developer → API Keys`:

```bash
omi auth refresh
```

Tancar la sessió:

```bash
omi auth logout
```

---

## 3. Ordres principals

### Memòries (memories)

Fets i coneixements que el sistema ha recordat sobre tu.

```bash
# llista de memòries
omi memory list

# crear-ne una de nova
omi memory create "L'usuari prefereix el tema fosc" --category lifestyle

# veure'n una de concreta
omi memory get <MEMORY_ID>
```

### Converses (conversations)

Historial de veu i text del dispositiu o de l'aplicació.

```bash
# les 5 converses més recents
omi conversation list --limit 5

# conversa sencera amb la transcripció
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tasques (action items)

Tasques que Omi ha extret de les converses.

```bash
# només les pendents
omi action-item list --open

# marcar-la com a feta
omi action-item complete <ACTION_ITEM_ID>
```

### Objectius (goals)

```bash
# llista d'objectius
omi goal list

# enregistrar un nou valor de progrés (calen TOTS DOS arguments: objectiu i valor)
omi goal progress <GOAL_ID> 25

# historial de canvis
omi goal history <GOAL_ID>
```

---

## Pregunta amb paraules teves (`ask`)

Ordre independent de nivell superior: fa una pregunta en llenguatge natural
i la resposta es construeix a partir de les teves pròpies converses.

```bash
omi ask "què vaig decidir sobre la mudança"
omi --json ask "quines tasques vaig prometre acabar aquesta setmana"
```

---

## 4. JSON i scripts (`--json`)

`omi-cli` pot retornar JSON llegible per màquina. El flag `--json` és **global**,
per tant va **abans** de la subordre.

```bash
# memòries: extreure id, text i categoria
omi --json memory list | jq '.[] | {id, content, category}'

# títols de les converses recents
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# tasques pendents
omi --json action-item list --open | jq '.'
```

> **Error freqüent.** `--json` va abans de la subordre, no després.
> * Correcte: `omi --json memory list`
> * Incorrecte: `omi memory list --json`

En mode `--json`, a la sortida estàndard no arriba res més que el JSON —
hi podeu confiar en els scripts.

---

## 5. Codis de sortida

Els codis són estables, així que els scripts i la CI hi poden ramificar la lògica.

| Codi | Significat | Quan ocorre |
| :---: | :--- | :--- |
| `0` | Èxit | L'ordre ha acabat |
| `1` | Error de crida | Validació pròpia d'omi-cli (p. ex. `--browser` i `--api-key` alhora, opció no vàlida, entrada buida) |
| `2` | Error d'accés o d'arguments | Sessió no iniciada, clau incorrecta o caducada — també errors de l'analitzador (flag desconegut, argument que falta) |
| `3` | Error de servidor | Resposta 5xx, timeout, sense connexió |
| `4` | Massa peticions | 429 Too Many Requests |
| `5` | No trobat | 404, l'identificador indicat no existeix |

Exemple de comprovació en Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "la clau funciona"
else
  code=$?
  [ "$code" -eq 2 ] && echo "cal tornar a iniciar sessió"
  [ "$code" -eq 3 ] && echo "servidor no disponible, reintenteu més tard"
fi
```

---

## 6. Variables d'entorn

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_la_teva_clau"

omi --json memory list --limit 10
```

Perquè la clau es carregui en sessions noves, afegiu la línia al `~/.bashrc` o `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_la_teva_clau"

# processar JSON amb PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Configuració permanent:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_la_teva_clau", "User")
```

---

## 7. Aplicació local Omi Desktop

Si l'aplicació d'escriptori Omi està en marxa, part de les dades són accessibles
directament, sense passar pel núvol.

```bash
# indicar l'adreça de l'API local
omi local configure --url http://127.0.0.1:47778 --token EL_TEU_TOKEN

# comprovar que respon
omi --json local status

# cercar a l'historial de pantalla
omi --json local search-screen "tarifes" --days 7 --app Safari

# captura de pantalla per identificador
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# consulta SQL lliure sobre la base de dades local
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Ordre de treball: primer `local status`, després `local tools` — per conèixer les
eines disponibles i els seus paràmetres — i només després les crides.

---

## 8. Perfils

Si teniu diversos comptes o entorns, separeu-los amb perfils.
La configuració es desa a `~/.omi/config.toml`.

```bash
# iniciar sessió al perfil personal
omi --profile personal auth login

# iniciar sessió al perfil de feina
omi --profile work auth login

# executar una ordre en un perfil concret
omi --profile work memory list
```

Si no especifiques cap perfil, el CLI usa primer el valor de la variable d'entorn `OMI_PROFILE`, després el perfil actiu del fitxer de configuració, i finalment `default`. Precedència: `--profile` → `OMI_PROFILE` → perfil actiu a `~/.omi/config.toml` → `default`.

Veure i modificar la pròpia configuració:

```bash
# què hi ha configurat ara
omi config show

# on és el fitxer de configuració
omi config path

# canviar un valor
omi config set api_base https://api.omi.me
```

---

## 9. I després

* [`agent_quickstart.md`](./agent_quickstart.md) — com connectar `omi-cli` a un agent d'IA.
* [`shell_examples.sh`](./shell_examples.sh) — exemples de shell ja preparats.
* [Documentació d'Omi](https://docs.omi.me/doc/developer/cli/introduction) — referència completa de les ordres.
