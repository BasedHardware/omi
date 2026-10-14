# omi-cli — svensk snabbstartsguide

> En praktisk guide för att arbeta med Omi från terminalen. Lämpar sig för både människor och AI-agenter.

`omi-cli` är den officiella kommandoradsklienten för [Omi](https://omi.me) utvecklar-API.
Den ger snabb och skriptbar åtkomst till Omis fyra kärnresurser:
minnen, samtal, åtgärdspunkter och mål.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Källkod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Den rekommenderade metoden är `pipx`: den installerar verktyget i en isolerad
miljö så att dess beroenden inte kolliderar med dina projekt.

```bash
# rekommenderat: installera med pipx
pipx install omi-cli

# eller med pip
pip install omi-cli
```

> **Viktigt: paketnamnet och kommandonamnet skiljer sig åt.**
> * Paketet som installeras är **`omi-cli`** (det separata paketet `omi` är ett annat, orelaterat projekt).
> * Efter installationen kör du kommandot **`omi`**.

Kontrollera att allt fungerar:

```bash
omi --version
omi --help
```

---

## 2. Autentisering

`omi-cli` stödjer två inloggningsmetoder.

| Metod | Lämpar sig för | Kommando |
| :--- | :--- | :--- |
| **Utvecklarnyckel (`omi_dev_*`)** | CI/CD, skript, AI-agenter | `omi auth login --api-key ...` eller miljövariabel |
| **Webbläsar-inloggning (Google/Apple)** | Arbete på din egen dator | `omi auth login --browser` |

### Interaktiv inloggning

Kör utan flaggor så frågar den vilken metod du vill använda.

```bash
omi auth login
# 1) Browser — logga in med Google eller Apple (för människor)
# 2) API key — klistra in en utvecklarnyckel från app.omi.me (för agenter/CI)
```

Väljer du nyckeln döljs inmatningen så att nyckeln inte hamnar i terminalhistoriken.

### Logga in direkt via webbläsaren

```bash
omi auth login --browser
```

### Logga in med utvecklarnyckel

Hämta nyckeln på [app.omi.me](https://app.omi.me) under **Developer → API Keys**.

```bash
# spara nyckeln i konfigurationen
omi auth login --api-key omi_dev_...

# eller skicka den via miljön — bättre för CI/CD och containrar
export OMI_API_KEY=omi_dev_...
```

Miljövariabeln `OMI_API_KEY` används när ingen nyckel är sparad i den aktiva profilen,
så i en container behöver ingenting skrivas till disk. Om profilen redan har en nyckel
har den företräde framför miljövariabeln.

### Verifiera åtkomsten

Två kommandon svarar på olika frågor och får inte förväxlas:

* `omi auth status` — vad som är sparat **lokalt**: profil, maskerad nyckel, utgångsdatum.
  Fungerar utan nätverk.
* `omi auth whoami` — en förfrågan **till Omi-servern**: verifierar att nyckeln verkligen accepteras.
  Kräver nätverk.

```bash
omi auth status    # lokal kontroll, offline
omi auth whoami    # kontroll på servern
```

Förnya en token som håller på att löpa ut utan att logga in igen — det här kommandot
gäller **bara för webbläsar-/OAuth-sessioner**. För en profil som autentiserats med en
API-nyckel (`omi_dev_*`) misslyckas `omi auth refresh` med ett användningsfel (kod 1):
det finns ingen token att förnya — byt nyckeln i Omi-webbappen vid behov:

```bash
omi auth refresh
```

Logga ut:

```bash
omi auth logout
```

---

## 3. Grundläggande kommandon

### Minnen (memories)

Fakta och kunskap som systemet lagrat om dig.

```bash
# lista minnen
omi memory list

# skapa ett nytt
omi memory create "Användaren föredrar mörkt tema" --category lifestyle

# visa ett specifikt
omi memory get <MEMORY_ID>
```

### Samtal (conversations)

Röst- och text Historik från enheten eller appen.

```bash
# de 5 senaste samtalen
omi conversation list --limit 5

# ett helt samtal med transkribering
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Åtgärdspunkter (action items)

Uppgifter som Omi härlett från samtal.

```bash
# bara de öppna
omi action-item list --open

# markera som slutförd
omi action-item complete <ACTION_ITEM_ID>
```

### Mål (goals)

```bash
# lista mål
omi goal list

# registrera ett nytt framstegsvärde (kräver BÅDA argumenten: mål och värde)
omi goal progress <GOAL_ID> 25

# historik över ändringar
omi goal history <GOAL_ID>
```

---

## Fråga på naturligt språk (`ask`)

Ett separat toppnivåkommando: det tar en fråga på naturligt språk,
och svaret byggs från dina samtal.

```bash
omi ask "vad beslutade jag om flytten"
omi --json ask "vilka åtgärdspunkter lovade jag att slutföra den här veckan"
```

---

## 4. JSON och skript (`--json`)

`omi-cli` kan producera maskinläsbar JSON. Flaggan `--json` är **global**
och måste placeras **före** underkommandot.

```bash
# minnen: extrahera id, text och kategori
omi --json memory list | jq '.[] | {id, content, category}'

# titlar på de senaste samtalen
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# öppna åtgärdspunkter
omi --json action-item list --open | jq '.'
```

> **Vanligt misstag.** `--json` kommer före underkommandot, inte efter.
> * Rätt: `omi --json memory list`
> * Fel: `omi memory list --json`

I `--json`-läget försvinner framstegsmeddelanden och spinnare för människor —
stdout innehåller bara ett giltigt JSON-dokument. Fel går till stderr
i formen `{"error": "...", "detail": "..."}`.

---

## 5. Utgångskoder

Stabila utgångskoder för att fatta beslut i skript.

| Kod | Betydelse |
| :--- | :--- |
| `0` | Framgång |
| `1` | Användningsfel (fel flagga, obligatoriskt argument saknas) |
| `2` | Autentisering misslyckades — inloggning krävs |
| `3` | Server-/nätverksfel |
| `4` | Hastighetsgräns — försök igen senare |
| `5` | Resursen hittades inte |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "det minnet finns inte" ;;
    *) echo "fel $code" ;;
  esac
fi
```

---

## 6. Profiler och konfiguration

Om du har flera konton eller miljöer, separera dem med profiler.
Inställningarna sparas i `~/.omi/config.toml`.

```bash
# logga in på den personliga profilen
omi --profile personal auth login

# logga in på arbetsprofilen
omi --profile work auth login

# kör ett kommando i en specifik profil
omi --profile work memory list
```

Profilen som används avgörs i denna ordning: flaggan `--profile` (eller `-p`)
har företräde framför allt; sedan miljövariabeln `OMI_PROFILE`; sedan den aktiva
profilen i `~/.omi/config.toml`; och slutligen profilen `default` som reserv.

Visa och ändra själva konfigurationen:

```bash
# vad som är inställt just nu
omi config show

# var konfigurationsfilen ligger
omi config path

# ändra ett värde
omi config set api_base https://api.omi.me
```

---

## 7. Nästa steg

* [`agent_quickstart.md`](./agent_quickstart.md) — hur du kopplar `omi-cli` till en AI-agent.
* [`shell_examples.sh`](./shell_examples.sh) — färdiga skalexempel.
* [Omi-dokumentation](https://docs.omi.me/doc/developer/cli/introduction) — fullständig kommandoreferens.
