# `omi-cli`

## Enkonduko

### Kio estas `omi-cli`?

`omi-cli` estas komandlinia interfaco (CLI), kiu permesas al vi **krei, ruli, monitori, halti kaj administri AI-agentojn rekte de la terminalo**.

Ĝi provizas simplan laborfluon por administri AI-agentojn sen bezono de grafika interfaco.

---

## Prerekvizitoj

Antaŭ ol uzi `omi-cli`, certigu, ke vi havas:

* Python 3.x instalita
* `pip` disponebla
* Postulataj akreditaĵoj de OMI API
* Rulanta loka OMI API, se vi uzas lokan agordon

---

## Instalado

Instalu `omi-cli` per pip:

```bash
pip install omi-cli
```

---

## Agordi API-ŝlosilojn

### Mediaj variabloj

Agordu la postulatajn mediajn variablojn antaŭ ol uzi la CLI.

### Linukso / macOS

```bash
export OMI_API_KEY="via_api_ŝlosilo"
export OMI_LOCAL_API_URL="http://localhost:8000"
export OMI_LOCAL_TOKEN="via_token"
```

### Vindoza PowerShell

```powershell
$env:OMI_API_KEY="via_api_ŝlosilo"
$env:OMI_LOCAL_API_URL="http://localhost:8000"
$env:OMI_LOCAL_TOKEN="via_token"
```

> Anstataŭigu `via_api_ŝlosilo` kaj `via_token` per viaj realaj akreditaĵoj.

---

# Administrado de Agentoj

## Krei Agenton

Kreu novan AI-agenton per:

```bash
omi agent create --name "MiaAgento"
```

Ekzemplo:

```bash
omi agent create --name "EsplorAgento"
```

---

## Ruli Agenton

Lanĉu ekzistantan agenton:

```bash
omi agent run --name "MiaAgento"
```

Ekzemplo:

```bash
omi agent run --name "EsplorAgento"
```

---

## Monitori Agenton

Kontrolu la nunan staton de agento:

```bash
omi agent status --name "MiaAgento"
```

Ekzemplo:

```bash
omi agent status --name "EsplorAgento"
```

Ĉi tio povas esti uzata por kontroli ĉu la agento funkcias aŭ estas haltigita.

---

## Halti Agenton

Haltigu rulantan agenton:

```bash
omi agent stop --name "MiaAgento"
```

Ekzemplo:

```bash
omi agent stop --name "EsplorAgento"
```

---

## Forigi Agenton

Forigu ekzistantan agenton:

```bash
omi agent delete --name "MiaAgento"
```

Ekzemplo:

```bash
omi agent delete --name "EsplorAgento"
```

---

# Kompleta Laborfluo

Tipa laborfluo aspektas jene:

### 1. Instali

```bash
pip install omi-cli
```

### 2. Agordi akreditaĵojn

```bash
export OMI_API_KEY="via_api_ŝlosilo"
export OMI_LOCAL_API_URL="http://localhost:8000"
export OMI_LOCAL_TOKEN="via_token"
```

### 3. Krei agenton

```bash
omi agent create --name "MiaAgento"
```

### 4. Ruli la agenton

```bash
omi agent run --name "MiaAgento"
```

### 5. Kontroli statuson

```bash
omi agent status --name "MiaAgento"
```

### 6. Halti la agenton

```bash
omi agent stop --name "MiaAgento"
```

### 7. Forigi la agenton

```bash
omi agent delete --name "MiaAgento"
```

---

# Komanda Referenco

| Komando                               | Priskribo          |
| ------------------------------------- | ------------------ |
| `omi agent create --name "MiaAgento"` | Krei novan agenton |
| `omi agent run --name "MiaAgento"`    | Lanĉi agenton      |
| `omi agent status --name "MiaAgento"` | Kontroli statuson  |
| `omi agent stop --name "MiaAgento"`   | Halti agenton      |
| `omi agent delete --name "MiaAgento"` | Forigi agenton     |

---

## Rapida Ekzemplo

```bash
# Instali
pip install omi-cli

# Agordi
export OMI_API_KEY="via_api_ŝlosilo"
export OMI_LOCAL_API_URL="http://localhost:8000"
export OMI_LOCAL_TOKEN="via_token"

# Krei
omi agent create --name "MiaAgento"

# Ruli
omi agent run --name "MiaAgento"

# Monitori
omi agent status --name "MiaAgento"

# Halti
omi agent stop --name "MiaAgento"

# Forigi
omi agent delete --name "MiaAgento"
```

---

## Resumo

`omi-cli` provizas simplan terminalan interfacon por administri AI-agentojn:

**Krei → Ruli → Monitori → Halti → Forigi**
