# Snabbstartsguide för omi-cli (Svenska)

> Praktisk guide för att interagera med Omi från terminalen. Lämplig för både människor och AI-agenter.

`omi-cli` är det officiella kommandoradsgränssnittet för att interagera med Omi:s ([omi.me](https://omi.me)) utvecklar-API:er. Det hanterar effektivt och skriptbart Omi:s fyra kärnresurser — **minnen, konversationer, åtgärdsposter och mål**.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Officiell dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Källkod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Den rekommenderade installationsmetoden är att använda `pipx` för att isolera beroenden.

```bash
# Rekommenderat: installera med pipx
pipx install omi-cli

# Alternativt: använd pip
pip install omi-cli
```

> **Viktigt: skillnad mellan paketnamn och kommandonamn**
> * Det installerade Python-paketet heter **`omi-cli`** (det fristående `omi`-paketet är ett annat, orelaterat paket).
> * Det exekverbara kommandot i terminalen efter installationen heter **`omi`**.

Kontrollera version och hjälp efter installationen.

```bash
omi --version
omi --help
```

---

## 2. Autentisering

`omi-cli` stöder två autentiseringsmetoder.

| Metod | Rekommenderad användning | Exempelkommando |
| :--- | :--- | :--- |
| **Utvecklar-API-nyckel (`omi_dev_*`)** | CI/CD, automatiska skript, AI-agenter | `omi auth login --api-key ...` eller miljövariabel |
| **Webbläsar-OAuth (Google/Apple)** | Utvecklar-PC / bärbar dator | `omi auth login --browser` |

### Interaktiv inloggning
Utan alternativ ombeds du att välja mellan webbläsarinloggning och API-nyckelinmatning.

```bash
omi auth login
# 1) Webbläsare — logga in med ditt Google- eller Apple-konto (för människor)
# 2) API-nyckel — klistra in utvecklarnyckeln från app.omi.me (för agenter/CI)
```

### Direkt inloggning via webbläsare
```bash
omi auth login --browser
```

### Använda API-nyckeln
Hämta utvecklarnyckeln från **Developer → API Keys** på [app.omi.me](https://app.omi.me) och ställ sedan in den.

```bash
# Ställ in via kommando
omi auth login --api-key omi_dev_...

# Eller via miljövariabel (idealisk för CI/CD eller containers)
export OMI_API_KEY=omi_dev_...
```

### Kontrollera autentiseringsstatus
* `omi auth status`: visar lokal profil, maskerad token och utgångsdatum (fungerar offline).
* `omi auth whoami`: skickar en riktig autentiseringsbegäran till Omi-servern (kräver nätverksanslutning).

```bash
omi auth status
omi auth whoami
```

För att logga ut:
```bash
omi auth logout
```

---

## 3. Grundläggande användning

Du kan lista och hantera Omi:s fyra kärnresurser.

### Minnen (Memories)
Hantera fakta och kunskap som systemet har lärt sig.

```bash
# Lista alla minnen
omi memory list

# Skapa ett nytt minne
omi memory create "Användaren föredrar mörkt läge" --category lifestyle

# Visa detaljer för ett specifikt minne
omi memory get <MEMORY_ID>
```

### Konversationer (Conversations)
Ljud- eller texthistorik för konversationer som fångats av den bärbara enheten eller appen.

```bash
# Hämta de senaste 5 konversationerna
omi conversation list --limit 5

# Visa konversationsdetaljer och transkription
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Åtgärdsposter (Action Items)
Uppgifter eller uppföljningsposter som automatiskt extraherats från konversationer.

```bash
# Lista endast öppna åtgärdsposter
omi action-item list --open

# Markera en åtgärdspost som slutförd
omi action-item complete <ACTION_ITEM_ID>
```

### Mål (Goals)
Hantera mål vars framsteg spåras.

```bash
# Lista alla mål
omi goal list
```

---

## 4. Scriptbearbetning och JSON-utdata (`--json`)

`omi-cli` stöder JSON-utdata internt. I kombination med `jq` eller Python-skript måste det **globala alternativet** `--json` placeras före underkommandot.

```bash
# Hämta minneslista som JSON och extrahera ID och innehåll
omi --json memory list | jq '.[] | {id, content, category}'

# Hämta titlarna på de senaste 5 konversationerna
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Lista öppna åtgärdsposter
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Lista mål
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Sessionsdiagnostik

Använd dessa två kommandon i par för snabb felsökning.

```bash
# 1) Kontrollera först den lokala konfigurationen
omi auth status

# 2) Bekräfta med Omi-servern
omi auth whoami

# 3) Starta om inloggningen om det behövs
omi auth login
```

---

## 6. Bästa praxis

* **Använd `--json` i skript:** Undvik att tolka fritext; förlita dig alltid på strukturerad JSON-utdata.
* **Isolera miljöer med `pipx`:** Undviker beroendekonflikter med andra Python-paket.
* **Dela inte API-nycklar:** `omi_dev_*`-nycklar ger full kontoåtkomst — förvara dem i en hemlighetshanterare eller miljövariabler.
* **Logga ut från delade enheter:** Använd `omi auth logout` efter sessioner på delade maskiner.

---

## 7. Felsökning

| Symtom | Trolig orsak | Lösning |
| :--- | :--- | :--- |
| `command not found: omi` | PATH innehåller inte pipx bin-katalogen | Kör `pipx ensurepath` och starta om terminalen |
| `401 Unauthorized` | API-nyckel är ogiltig eller har gått ut | Generera en ny nyckel på app.omi.me och uppdatera |
| `connection refused` | Ingen nätverksåtkomst till Omi-servern | Kontrollera internetanslutning och proxyinställningar |
| `permission denied` på konfigurationsfiler | Konfigurationskatalogen är inte skrivbar | Kontrollera behörigheterna för `~/.omi/config.toml` |

---

## 8. Snabblänkar

* Källrepo: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Fullständig dokumentation: [docs.omi.me](https://docs.omi.me)
* Ärenden och support: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Discord-community: inbjudan tillgänglig via Omi:s hemsida