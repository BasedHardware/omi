# Omi CLI: быстрый старт

Omi CLI позволяет работать с памятью, разговорами, задачами и целями из терминала.
Команда называется `omi`, а пакет для установки называется `omi-cli`.

[English README](README.md) · [Справка по командам](https://docs.omi.me/doc/developer/cli/commands)

## Установка

Нужен Python 3.10 или новее. Если у тебя установлен pipx:

```bash
pipx install omi-cli
omi --version
```

Другой вариант: отдельное окружение Python:

```bash
python -m venv .venv
```

Активируй его в macOS или Linux:

```bash
source .venv/bin/activate
```

В Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

После активации:

```bash
python -m pip install omi-cli
omi --help
```

## Вход

Запусти интерактивный вход и выбери браузер или API-ключ:

```bash
omi auth login
```

Для входа через браузер можно сразу указать способ:

```bash
omi auth login --browser
```

Проверить сохранённый профиль и доступ к серверу:

```bash
omi auth status
omi auth whoami
```

`status` показывает локальное состояние входа, а `whoami` отправляет запрос к API.
Не добавляй ключи в код, скриншоты или публичные сообщения. Для автоматизации CLI
также поддерживает переменную окружения `OMI_API_KEY`.

## Прочитать данные

```bash
omi memory list --limit 10
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Память загружается по страницам. Следующую страницу можно получить через `--offset`:

```bash
omi memory list --limit 25 --offset 25
```

Для обращения к конкретной записи используй её полный `id`. Надёжнее всего взять
его из JSON: табличный вывод может сокращать длинные идентификаторы.

## JSON для скриптов

Глобальный флаг `--json` ставится перед названием команды:

```bash
omi --json memory list --limit 10
omi --json action-item list --open
```

Если установлен jq, можно вывести только нужные поля:

```bash
omi --json memory list | jq '.[] | {id, content}'
```

Ошибки проверяй по коду завершения процесса. Команды чтения и записи могут
возвращать разные формы ответа; отдельные команды в текущей версии ещё не выдают
JSON при успешном выполнении. Не считай пустой вывод доказательством ошибки.

## Создать и изменить записи

Следующие команды создают данные в аккаунте:

```bash
omi memory create "Предпочитаю короткие отчёты" --category work --tag preferences
omi action-item create "Проверить отчёт"
omi goal create "Читать каждый день" --type numeric --target 20 --unit minutes
```

В примерах ниже замени `MEMORY_ID` и `GOAL_ID` полными идентификаторами своих записей:

```bash
omi memory update MEMORY_ID --content "Предпочитаю короткие отчёты с примерами"
omi goal progress GOAL_ID 5
```

Удаление запрашивает подтверждение. `--yes` отключает этот вопрос, поэтому не
используй его при проверке незнакомой команды:

```bash
omi memory delete MEMORY_ID
```

## Профили и выход

Настройки обычно хранятся в `~/.omi/config.toml`; путь можно изменить переменной
`OMI_CONFIG`. Чтобы переключить профиль:

```bash
omi config profile use work
omi auth login
omi --profile work memory list
```

Завершить сеанс в активном профиле:

```bash
omi auth logout
```

## Если что-то не работает

- `omi` не найдена: проверь активацию окружения или настройку PATH для pipx.
- Нет доступа к API: выполни `omi auth whoami`, затем при необходимости войди заново.
- Неизвестный параметр: посмотри справку нужной команды, например `omi goal create --help`.
- Работа с локальной историей экрана: команды `omi local` требуют запущенного
  Omi Desktop и настройки его локального API; обычного облачного входа недостаточно.

Полное описание параметров, лимитов API и кодов завершения есть в
[основном README](README.md).
