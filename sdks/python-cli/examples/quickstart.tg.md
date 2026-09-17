# omi-cli Роҳнамои оғози сареъ ба забони тоҷикӣ

> Бо Omi аз сатри фармон (терминал) муколама кунед. Барои одамон **ва** агентҳои AI сохта шудааст.

`omi-cli` интерфейси сатри фармон (CLI) барои [Omi](https://omi.me) Developer API мебошад.
Он фармонҳои мувофиқро барои чор манбаи асосӣ пешниҳод мекунад:

* **memories** — Далелҳо ва ёддоштҳо
* **conversations** — Гуфтугӯҳои сабтшуда ва коркардшуда бо матн
* **action items** — Вазифаҳо ва амалҳои пайгирӣ
* **goals** — Метрикаҳои пешрафти пайгиришаванда

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Ҳуҷҷатҳо:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)

---

## 1. Насбкунӣ

Барои насби ҷудогона ва бехатар тавсия мешавад аз `pipx` истифода баред:

```bash
pipx install omi-cli
# ё бо pip
pip install omi-cli
```

> **Эзоҳ:** Номи баста дар PyPI `omi-cli` мебошад. Фармони иҷрошаванда дар терминал `omi` аст.

Пас аз насб санҷед:

```bash
omi --version
omi --help
```

---

## 2. Муайянкунии шахсият (Аутентификатсия)

| Усул | Истифода | Фармон |
| :--- | :--- | :--- |
| **API-Key** (`omi_dev_*`) | CI/CD, Скриптҳо, Агентҳо | `omi auth login --api-key ...` |
| **Браузер** (Google/Apple) | Истифодаи шахсӣ | `omi auth login --browser` |

### Воридшавии интерактивии сатри фармон

```bash
omi auth login
# 1) Браузер → Google ё Apple (барои одамон)
# 2) API key → Калиди таҳиякунанда аз app.omi.me (барои агентҳо/CI)
```

### Калиди API (Developer Key)

Аз вебсайти [app.omi.me](https://app.omi.me) дар бахши **Developer → API Keys** дастрас кунед:

```bash
omi auth login --api-key omi_dev_...
# ё тавассути тағйирёбандаи муҳит (Environment Variable)
export OMI_API_KEY=omi_dev_...
```

### Санҷиши ҳолати воридшавӣ

```bash
omi auth status    # Ҳолати маҳаллӣ (local status)
omi auth whoami    # Тасдиқи калид дар сервер
```

---

## 3. Хондан ва гирифтани маълумот

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

| Фармон | Тавсиф |
| --- | --- |
| `memory` | Далелҳо ва хотираҳои шахсӣ |
| `conversation` | Гуфтугӯҳо ва стенограммаҳо |
| `action-item` | Вазифаҳо ва супоришҳо |
| `goal` | Ҳадафҳо ва пешрафт |

---

## 4. Натиҷаи JSON барои скриптҳо ва автоматизатсия

Опсияи умумии `--json` бояд **пеш** аз гурӯҳи фармонҳо гузошта шавад:

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

### Дар скриптҳои Shell (Bash):

```bash
ids=$(omi --json memory list --limit 5 | jq -r '.[].id')
for id in $ids; do
  echo "Коркарди хотира: $id"
done
```

### Дар Python:

```python
import subprocess, json

result = subprocess.run(
    ["omi", "--json", "memory", "list", "--limit", "5"],
    capture_output=True, text=True
)
memories = json.loads(result.stdout)
for m in memories:
    print(m["id"], m.get("content", "")[:80])
```

---

## 5. Рамзҳои баромад (Exit Codes)

| Рамз | Маънӣ | Ҳолат / Амал |
| :---: | :--- | :--- |
| `0` | Муваффақият | Фармон бомуваффақият иҷро шуд |
| `1` | Хатогии истифода | Парчам ё аргументи нодуруст |
| `2` | Хатогии дастрасӣ | Калид нодуруст аст ё `omi auth login` лозим аст |
| `3` | Хатогии сервер | Хатогии 5xx, таваққуфи вақт (timeout) ё қатъи пайваст |
| `4` | Маҳдудияти дархостҳо | 429 Too Many Requests (дархостҳои аз ҳад зиёд) |
| `5` | Ёфт нашуд | 404 Not Found (захира ёфт нашуд) |

---

## Маълумоти иловагӣ

* Маълумотномаи мукаммал: `omi --help`
* Ҳуҷҷатҳои расмӣ: [docs.omi.me](https://docs.omi.me/doc/developer/cli/introduction)
* Саволҳо ва мушкилот: [GitHub Issues](https://github.com/BasedHardware/omi/issues)

---
*Bounty: Closes #14237*
