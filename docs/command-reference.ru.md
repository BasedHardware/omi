# Справочник команд omi CLI

Синтаксис проверен по [исходникам CLI](https://github.com/BasedHardware/omi/tree/37a92d3f024745d5fc62b7d3082e1c29a9789557/sdks/python-cli/omi_cli/) на коммите `37a92d3f024745d5fc62b7d3082e1c29a9789557`. Найдено команд: 48.

`<имя>` обозначает значение; квадратные скобки — необязательную часть и не вводятся. Флаги без значения включаются своим именем. Если указано несколько имён опции, это альтернативные формы. `|` обозначает выбор одного из двух флагов и тоже не вводится. Глобальные параметры доступны через `omi --help`; справка команды — через `omi <команда> --help`.

## Команды

### `omi action-item complete <action_item_id>`

- Позиционный аргумент `action_item_id`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/action_item.py:152`.

### `omi action-item create <description> [--completed | --open] [--due-at <due_at>]`

- Позиционный аргумент `description`: обязательный.
- Опция `--completed или --open`: необязательный; флаг без значения; по умолчанию `False`.
- Опция `--due-at`: необязательный; по умолчанию `None`.

Исходник: `sdks/python-cli/omi_cli/commands/action_item.py:103`.

### `omi action-item delete <action_item_id> [--yes]`

- Позиционный аргумент `action_item_id`: обязательный.
- Опция `--yes, -y`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/action_item.py:164`.

### `omi action-item get <action_item_id>`

- Позиционный аргумент `action_item_id`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/action_item.py:73`.

### `omi action-item list [--completed | --open] [--conversation-id <conversation_id>] [--start-date <start_date>] [--end-date <end_date>] [--limit <limit>] [--offset <offset>]`

- Опция `--completed или --open`: необязательный; флаг без значения; по умолчанию `None`.
- Опция `--conversation-id`: необязательный; по умолчанию `None`.
- Опция `--start-date`: необязательный; по умолчанию `None`.
- Опция `--end-date`: необязательный; по умолчанию `None`.
- Опция `--limit`: необязательный; по умолчанию `100`.
- Опция `--offset`: необязательный; по умолчанию `0`.

Исходник: `sdks/python-cli/omi_cli/commands/action_item.py:32`.

### `omi action-item update <action_item_id> [--description <description>] [--completed | --open] [--due-at <due_at>] [--clear-due-at]`

- Позиционный аргумент `action_item_id`: обязательный.
- Опция `--description`: необязательный; по умолчанию `None`.
- Опция `--completed или --open`: необязательный; флаг без значения; по умолчанию `None`.
- Опция `--due-at`: необязательный; по умолчанию `None`.
- Опция `--clear-due-at`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/action_item.py:120`.

### `omi ask <question> [--limit <limit>] [--timezone <timezone>]`

- Позиционный аргумент `question`: обязательный.
- Опция `--limit`: необязательный; по умолчанию `5`.
- Опция `--timezone`: необязательный; по умолчанию `'UTC'`.

Исходник: `sdks/python-cli/omi_cli/main.py:164`.

### `omi auth login [--api-key <api_key_arg>] [--browser] [--provider <provider>]`

- Опция `--api-key`: необязательный; по умолчанию `None`.
- Опция `--browser`: необязательный; флаг без значения; по умолчанию `False`.
- Опция `--provider`: необязательный; по умолчанию `'google'`.

Исходник: `sdks/python-cli/omi_cli/commands/auth.py:34`.

### `omi auth logout`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/auth.py:172`.

### `omi auth refresh`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/auth.py:219`.

### `omi auth status`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/auth.py:184`.

### `omi auth whoami`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/auth.py:201`.

### `omi config path`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/config.py:55`.

### `omi config profile delete <name> [--yes]`

- Позиционный аргумент `name`: обязательный.
- Опция `--yes, -y`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/config.py:144`.

### `omi config profile list`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/config.py:101`.

### `omi config profile use <name>`

- Позиционный аргумент `name`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/config.py:126`.

### `omi config set <key> <value>`

- Позиционный аргумент `key`: обязательный.
- Позиционный аргумент `value`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/config.py:68`.

### `omi config show`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/config.py:30`.

### `omi conversation create [--text <text>] [--text-source <text_source>] [--text-source-spec <text_source_spec>] [--started-at <started_at>] [--finished-at <finished_at>] [--language <language>]`

- Опция `--text`: необязательный; по умолчанию `None`.
- Опция `--text-source`: необязательный; по умолчанию `ConversationTextSource.other_text`.
- Опция `--text-source-spec`: необязательный; по умолчанию `None`.
- Опция `--started-at`: необязательный; по умолчанию `None`.
- Опция `--finished-at`: необязательный; по умолчанию `None`.
- Опция `--language`: необязательный; по умолчанию `'en'`.

Исходник: `sdks/python-cli/omi_cli/commands/conversation.py:121`.

### `omi conversation delete <conversation_id> [--yes]`

- Позиционный аргумент `conversation_id`: обязательный.
- Опция `--yes, -y`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/conversation.py:236`.

### `omi conversation from-segments <segments_file> [--source <source>] [--started-at <started_at>] [--finished-at <finished_at>] [--language <language>]`

- Позиционный аргумент `segments_file`: обязательный.
- Опция `--source`: необязательный; по умолчанию `None`.
- Опция `--started-at`: необязательный; по умолчанию `None`.
- Опция `--finished-at`: необязательный; по умолчанию `None`.
- Опция `--language`: необязательный; по умолчанию `'en'`.

Исходник: `sdks/python-cli/omi_cli/commands/conversation.py:167`.

### `omi conversation get <conversation_id> [--include-transcript]`

- Позиционный аргумент `conversation_id`: обязательный.
- Опция `--include-transcript`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/conversation.py:106`.

### `omi conversation list [--limit <limit>] [--offset <offset>] [--start-date <start_date>] [--end-date <end_date>] [--categories <categories>] [--include-transcript]`

- Опция `--limit`: необязательный; по умолчанию `25`.
- Опция `--offset`: необязательный; по умолчанию `0`.
- Опция `--start-date`: необязательный; по умолчанию `None`.
- Опция `--end-date`: необязательный; по умолчанию `None`.
- Опция `--categories`: необязательный; по умолчанию `None`.
- Опция `--include-transcript`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/conversation.py:36`.

### `omi conversation update <conversation_id> [--title <title>] [--discarded | --no-discarded]`

- Позиционный аргумент `conversation_id`: обязательный.
- Опция `--title`: необязательный; по умолчанию `None`.
- Опция `--discarded или --no-discarded`: необязательный; флаг без значения; по умолчанию `None`.

Исходник: `sdks/python-cli/omi_cli/commands/conversation.py:215`.

### `omi goal create <title> [--target <target_value>] [--type <goal_type>] [--current <current_value>] [--min <min_value>] [--max <max_value>] [--unit <unit>]`

- Позиционный аргумент `title`: обязательный.
- Опция `--target`: необязательный; по умолчанию `None`.
- Опция `--type`: необязательный; по умолчанию `None`.
- Опция `--current`: необязательный; по умолчанию `None`.
- Опция `--min`: необязательный; по умолчанию `None`.
- Опция `--max`: необязательный; по умолчанию `None`.
- Опция `--unit`: необязательный; по умолчанию `None`.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:75`.

### `omi goal delete <goal_id> [--yes]`

- Позиционный аргумент `goal_id`: обязательный.
- Опция `--yes, -y`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:192`.

### `omi goal get <goal_id>`

- Позиционный аргумент `goal_id`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:62`.

### `omi goal history <goal_id> [--days <days>]`

- Позиционный аргумент `goal_id`: обязательный.
- Опция `--days`: необязательный; по умолчанию `30`.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:180`.

### `omi goal list [--limit <limit>] [--include-inactive]`

- Опция `--limit`: необязательный; по умолчанию `10`.
- Опция `--include-inactive`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:31`.

### `omi goal progress <goal_id> <current_value>`

- Позиционный аргумент `goal_id`: обязательный.
- Позиционный аргумент `current_value`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:166`.

### `omi goal update <goal_id> [--title <title>] [--target <target_value>] [--current <current_value>] [--min <min_value>] [--max <max_value>] [--unit <unit>] [--clear-unit]`

- Позиционный аргумент `goal_id`: обязательный.
- Опция `--title`: необязательный; по умолчанию `None`.
- Опция `--target`: необязательный; по умолчанию `None`.
- Опция `--current`: необязательный; по умолчанию `None`.
- Опция `--min`: необязательный; по умолчанию `None`.
- Опция `--max`: необязательный; по умолчанию `None`.
- Опция `--unit`: необязательный; по умолчанию `None`.
- Опция `--clear-unit`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/goal.py:125`.

### `omi local call <tool_name> [--args-json <args_json>]`

- Позиционный аргумент `tool_name`: обязательный.
- Опция `--args-json`: необязательный; по умолчанию `'{}'`.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:97`.

### `omi local configure --url <url> --token <token>`

- Опция `--url`: обязательный.
- Опция `--token`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:49`.

### `omi local recap [--days-ago <days_ago>]`

- Опция `--days-ago`: необязательный; по умолчанию `0`.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:166`.

### `omi local screenshot <screenshot_id> [--output <output>]`

- Позиционный аргумент `screenshot_id`: обязательный.
- Опция `--output, -o`: необязательный; по умолчанию `None`.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:136`.

### `omi local search-screen <query> [--days <days>] [--app <app_filter>] [--limit <limit>]`

- Позиционный аргумент `query`: обязательный.
- Опция `--days`: необязательный; по умолчанию `7`.
- Опция `--app`: необязательный; по умолчанию `None`.
- Опция `--limit`: необязательный; по умолчанию `15`.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:113`.

### `omi local sql <query>`

- Позиционный аргумент `query`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:175`.

### `omi local status`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:72`.

### `omi local task complete <task_id>`

- Позиционный аргумент `task_id`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:194`.

### `omi local task delete <task_id> [--yes]`

- Позиционный аргумент `task_id`: обязательный.
- Опция `--yes, -y`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:203`.

### `omi local task search <query> [--include-completed]`

- Позиционный аргумент `query`: обязательный.
- Опция `--include-completed`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:184`.

### `omi local tools`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/commands/local.py:89`.

### `omi memory create <content> [--category <category>] [--visibility <visibility>] [--tag <tag>]`

- Позиционный аргумент `content`: обязательный.
- Опция `--category`: необязательный; по умолчанию `None`.
- Опция `--visibility`: необязательный; по умолчанию `MemoryVisibility.private`.
- Опция `--tag`: необязательный; по умолчанию `[]`; можно повторять.

Исходник: `sdks/python-cli/omi_cli/commands/memory.py:95`.

### `omi memory delete <memory_id> [--yes]`

- Позиционный аргумент `memory_id`: обязательный.
- Опция `--yes, -y`: необязательный; флаг без значения; по умолчанию `False`.

Исходник: `sdks/python-cli/omi_cli/commands/memory.py:142`.

### `omi memory get <memory_id>`

- Позиционный аргумент `memory_id`: обязательный.

Исходник: `sdks/python-cli/omi_cli/commands/memory.py:66`.

### `omi memory list [--limit <limit>] [--offset <offset>] [--categories <categories>]`

- Опция `--limit`: необязательный; по умолчанию `25`.
- Опция `--offset`: необязательный; по умолчанию `0`.
- Опция `--categories`: необязательный; по умолчанию `None`.

Исходник: `sdks/python-cli/omi_cli/commands/memory.py:31`.

### `omi memory update <memory_id> [--content <content>] [--category <category>] [--visibility <visibility>] [--tag <tag>]`

- Позиционный аргумент `memory_id`: обязательный.
- Опция `--content`: необязательный; по умолчанию `None`.
- Опция `--category`: необязательный; по умолчанию `None`.
- Опция `--visibility`: необязательный; по умолчанию `None`.
- Опция `--tag`: необязательный; по умолчанию `None`; можно повторять.

Исходник: `sdks/python-cli/omi_cli/commands/memory.py:113`.

### `omi version`

Параметров команды нет.

Исходник: `sdks/python-cli/omi_cli/main.py:155`.
