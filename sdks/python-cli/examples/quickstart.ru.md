# omi-cli — быстрый старт на русском

> Практическое руководство по работе с Omi из терминала. Подходит и человеку, и ИИ-агенту.

`omi-cli` — официальный интерфейс командной строки для разработческого API [Omi](https://omi.me).
Он даёт быстрый и пригодный для скриптов доступ к четырём основным сущностям Omi:
воспоминаниям, разговорам, задачам и целям.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Документация:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Исходный код:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Установка

Рекомендуемый способ — `pipx`: он ставит утилиту в изолированное окружение,
поэтому её зависимости не конфликтуют с вашими проектами.

```bash
# рекомендуется: установка через pipx
pipx install omi-cli

# либо через pip
pip install omi-cli
```

> **Важно: имя пакета и имя команды различаются.**
> * Устанавливается пакет **`omi-cli`** (отдельный пакет `omi` — это другой, не связанный проект).
> * Запускается после установки команда **`omi`**.

Проверьте, что всё встало:

```bash
omi --version
omi --help
```

---

## 2. Аутентификация

`omi-cli` поддерживает два способа входа.

| Способ | Когда подходит | Команда |
| :--- | :--- | :--- |
| **Ключ разработчика (`omi_dev_*`)** | CI/CD, скрипты, ИИ-агенты | `omi auth login --api-key ...` или переменная окружения |
| **Вход через браузер (Google/Apple)** | Работа за своим компьютером | `omi auth login --browser` |

### Интерактивный вход

Без флагов команда сама спросит, каким способом входить:

```bash
omi auth login
# 1) Browser — вход через Google или Apple (удобно человеку)
# 2) API key — вставить ключ разработчика с app.omi.me (удобно агентам и CI)
```

При выборе ключа ввод маскируется, поэтому ключ не останется в истории терминала.

### Сразу через браузер

```bash
omi auth login --browser
```

### Через ключ разработчика

Ключ берётся на [app.omi.me](https://app.omi.me) в разделе **Developer → API Keys**.

```bash
# сохранить ключ в конфигурацию
omi auth login --api-key omi_dev_...

# либо передать через окружение — предпочтительно для CI/CD и контейнеров
export OMI_API_KEY=omi_dev_...
```

Переменная `OMI_API_KEY` используется, когда в активном профиле ключ не сохранён,
поэтому в контейнере не нужно ничего записывать на диск. Если ключ в профиле
уже есть, он имеет приоритет над переменной окружения.

### Проверка входа

Две команды отвечают на разные вопросы, и путать их не стоит:

* `omi auth status` — что лежит **локально**: профиль, маскированный ключ, срок действия.
  Работает без сети.
* `omi auth whoami` — обращение **к серверу Omi**: проверяет, что ключ действительно
  принимается. Нужна сеть.

```bash
omi auth status    # локальная проверка, офлайн
omi auth whoami    # проверка на сервере
```

Обновить истекающий токен без повторного входа:

```bash
omi auth refresh
```

Выход:

```bash
omi auth logout
```

---

## 3. Основные команды

### Воспоминания (memories)

Факты и знания, которые система запомнила о вас.

```bash
# список воспоминаний
omi memory list

# создать новое
omi memory create "Пользователь предпочитает тёмную тему" --category lifestyle

# посмотреть конкретное
omi memory get <MEMORY_ID>
```

### Разговоры (conversations)

История речи и текста с устройства или из приложения.

```bash
# последние 5 разговоров
omi conversation list --limit 5

# разговор целиком, вместе с расшифровкой
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Задачи (action items)

Дела, которые Omi выделил из разговоров.

```bash
# только невыполненные
omi action-item list --open

# отметить выполненной
omi action-item complete <ACTION_ITEM_ID>
```

### Цели (goals)

```bash
# список целей
omi goal list

# записать новое значение прогресса (нужны ОБА аргумента: цель и значение)
omi goal progress <GOAL_ID> 25

# история изменений
omi goal history <GOAL_ID>
```

---

## Вопрос своими словами (`ask`)

Отдельная команда верхнего уровня: задаёт вопрос на естественном языке,
ответ строится по вашим же разговорам.

```bash
omi ask "что я решил по поводу переезда"
omi --json ask "какие задачи я обещал закрыть на этой неделе"
```

---

## 4. JSON и скрипты (`--json`)

`omi-cli` умеет отдавать машинночитаемый JSON. Флаг `--json` — **глобальный**,
поэтому ставится **перед** подкомандой.

```bash
# воспоминания: вытащить id, текст и категорию
omi --json memory list | jq '.[] | {id, content, category}'

# заголовки последних разговоров
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# невыполненные задачи
omi --json action-item list --open | jq '.'
```

> **Частая ошибка.** `--json` идёт до подкоманды, а не после неё.
> * Правильно: `omi --json memory list`
> * Неправильно: `omi memory list --json`

В режиме `--json` в стандартный вывод не попадает ничего, кроме самого JSON, —
на это можно опираться в скриптах.

---

## 5. Коды возврата

Коды стабильны, поэтому по ним можно ветвить логику в скриптах и CI.

| Код | Значение | Когда возникает |
| :---: | :--- | :--- |
| `0` | Успех | Команда отработала |
| `1` | Ошибка вызова | Неверный флаг, не хватает аргумента |
| `2` | Ошибка доступа | Не выполнен вход, ключ неверен или просрочен |
| `3` | Ошибка сервера | Ответ 5xx, таймаут, нет связи |
| `4` | Слишком много запросов | 429 Too Many Requests |
| `5` | Не найдено | 404, указанный идентификатор не существует |

Пример проверки в Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "ключ рабочий"
else
  code=$?
  [ "$code" -eq 2 ] && echo "нужен повторный вход"
  [ "$code" -eq 3 ] && echo "сервер недоступен, повторить позже"
fi
```

---

## 6. Переменные окружения

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_ваш_ключ"

omi --json memory list --limit 10
```

Чтобы ключ подхватывался в новых сессиях, добавьте строку в `~/.bashrc` или `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_ваш_ключ"

# разбор JSON средствами PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Для постоянной установки:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_ваш_ключ", "User")
```

---

## 7. Локальное приложение Omi Desktop

Если запущено настольное приложение Omi, часть данных доступна напрямую,
минуя облако.

```bash
# указать адрес локального API
omi local configure --url http://127.0.0.1:47778 --token ВАШ_ТОКЕН

# проверить, что оно отвечает
omi --json local status

# поиск по истории экрана
omi --json local search-screen "тарифы" --days 7 --app Safari

# снимок экрана по идентификатору
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# произвольный SQL по локальной базе
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Порядок работы: сначала `local status`, затем `local tools` — чтобы узнать доступные
инструменты и их параметры, и только потом вызовы.

---

## 8. Профили

Если аккаунтов или окружений несколько, разделите их профилями.
Настройки хранятся в `~/.omi/config.toml`.

```bash
# вход в личный профиль
omi --profile personal auth login

# вход в рабочий
omi --profile work auth login

# выполнить команду в конкретном профиле
omi --profile work memory list
```

Посмотреть и поменять саму конфигурацию:

```bash
# что сейчас настроено
omi config show

# где лежит файл конфигурации
omi config path

# изменить значение
omi config set api_base https://api.omi.me
```

---

## 9. Что дальше

* [`agent_quickstart.md`](./agent_quickstart.md) — как подключить `omi-cli` к ИИ-агенту.
* [`shell_examples.sh`](./shell_examples.sh) — готовые примеры для оболочки.
* [Документация Omi](https://docs.omi.me/doc/developer/cli/introduction) — полный справочник команд.
