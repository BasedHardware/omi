# omi-cli за агенти

> Практическо ръководство за среди, управлявани от LLM (Claude Code, Cursor, персонализирани ботове).

## Защо CLI е удобен за агенти

* **Стабилен JSON договор.** Флагът `--json` извежда валиден JSON документ на stdout и *единствено* JSON документ — без съобщения за напредък, без анимации за зареждане. Грешките се изпращат към stderr във формат `{"error": "...", "detail": "..."}`.
* **Стабилни кодове за изход.** `0` успешно / `1` грешка при използване / `2` грешка при удостоверяване / `3` грешка на сървъра / `4` превишен лимит на заявките / `5` не е намерено. Агентите могат да вземат решения въз основа на тези кодове, без да анализират съобщения на естествен език.
* **Без интерактивни подкани в headless режим.** Подайте `--yes` (или `-y`) за деструктивни команди; подайте `--api-key` или задайте променливата `OMI_API_KEY`, за да пропуснете интерактивното влизане.
* **Гъвкаво поведение при повторен опит.** Кодовете за грешка `429` и `5xx` се повтарят автоматично с експоненциално забавяне (backoff) преди връщане на грешка.

## Автентикация (еднократна, извършва се от човек)

Потребителят взима API ключ за разработчици от уеб приложението Omi
(`https://app.omi.me` → Developer → API Keys) и изпълнява едно от следните:

```bash
omi auth login                          # интерактивно поставяне; ключът не се записва в историята на обвивката
# или
export OMI_API_KEY=omi_dev_...          # временно, подходящо за контейнери
```

## Петте най-чести действия на агентите

### 1. Четене на спомени (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Създаване на спомен

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Четене на разговори

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Четене на отворени задачи (action items)

```bash
omi action-item list --json --open
```

### 5. Маркиране на задача като завършена

```bash
omi action-item complete --json a1b2c3d4
```

## Локално Desktop API (Local Desktop API)

Когато Omi Desktop активира своето локално API, агентите могат да правят справки в историята на екрана на устройството, обобщения, SQL и задачи, без да използват облачното API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# или за временни сесии:
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

Завършвайте или изтривайте задачи само когато потребителят изрично поиска това:

```bash
omi --json local task complete task_1
```
