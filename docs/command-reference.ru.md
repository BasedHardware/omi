# Справочник команд omi

## Команды

### `action_item complete <action_item_id>`

Обязательные аргументы: `action_item_id`.

### `action_item create <description> [completed] [due_at]`

Обязательные аргументы: `description`.
Необязательные: `completed`, `due_at`.

### `action_item delete <action_item_id> [confirm]`

Обязательные аргументы: `action_item_id`.
Необязательные: `confirm`.

### `action_item get <action_item_id>`

Обязательные аргументы: `action_item_id`.

### `action_item list [completed] [conversation_id] [start_date] [end_date] [limit] [offset]`

Обязательных аргументов нет.
Необязательные: `completed`, `conversation_id`, `start_date`, `end_date`, `limit`, `offset`.

### `action_item update <action_item_id> [description] [completed] [due_at] [clear_due_at]`

Обязательные аргументы: `action_item_id`.
Необязательные: `description`, `completed`, `due_at`, `clear_due_at`.

### `auth login [api_key_arg] [browser] [provider]`

Обязательных аргументов нет.
Необязательные: `api_key_arg`, `browser`, `provider`.

### `auth logout`

Обязательных аргументов нет.

### `auth refresh`

Обязательных аргументов нет.

### `auth status`

Обязательных аргументов нет.

### `auth whoami`

Обязательных аргументов нет.

### `config delete <name> [confirm]`

Обязательные аргументы: `name`.
Необязательные: `confirm`.

### `config list`

Обязательных аргументов нет.

### `config path`

Обязательных аргументов нет.

### `config set <key> <value>`

Обязательные аргументы: `key`, `value`.

### `config show`

Обязательных аргументов нет.

### `config use <name>`

Обязательные аргументы: `name`.

### `conversation create <text_source> [text] [text_source_spec] [started_at] [finished_at] [language]`

Обязательные аргументы: `text_source`.
Необязательные: `text`, `text_source_spec`, `started_at`, `finished_at`, `language`.

### `conversation delete <conversation_id> [confirm]`

Обязательные аргументы: `conversation_id`.
Необязательные: `confirm`.

### `conversation from-segments <segments_file> [source] [started_at] [finished_at] [language]`

Обязательные аргументы: `segments_file`.
Необязательные: `source`, `started_at`, `finished_at`, `language`.

### `conversation get <conversation_id> [include_transcript]`

Обязательные аргументы: `conversation_id`.
Необязательные: `include_transcript`.

### `conversation list [limit] [offset] [start_date] [end_date] [categories] [include_transcript]`

Обязательных аргументов нет.
Необязательные: `limit`, `offset`, `start_date`, `end_date`, `categories`, `include_transcript`.

### `conversation update <conversation_id> [title] [discarded]`

Обязательные аргументы: `conversation_id`.
Необязательные: `title`, `discarded`.

### `goal create <title> [target_value] [goal_type] [current_value] [min_value] [max_value] [unit]`

Обязательные аргументы: `title`.
Необязательные: `target_value`, `goal_type`, `current_value`, `min_value`, `max_value`, `unit`.

### `goal delete <goal_id> [confirm]`

Обязательные аргументы: `goal_id`.
Необязательные: `confirm`.

### `goal get <goal_id>`

Обязательные аргументы: `goal_id`.

### `goal history <goal_id> [days]`

Обязательные аргументы: `goal_id`.
Необязательные: `days`.

### `goal list [limit] [include_inactive]`

Обязательных аргументов нет.
Необязательные: `limit`, `include_inactive`.

### `goal progress <goal_id> <current_value>`

Обязательные аргументы: `goal_id`, `current_value`.

### `goal update <goal_id> [title] [target_value] [current_value] [min_value] [max_value] [unit] [clear_unit]`

Обязательные аргументы: `goal_id`.
Необязательные: `title`, `target_value`, `current_value`, `min_value`, `max_value`, `unit`, `clear_unit`.

### `local call <tool_name> [args_json]`

Обязательные аргументы: `tool_name`.
Необязательные: `args_json`.

### `local complete <task_id>`

Обязательные аргументы: `task_id`.

### `local configure <url> <token>`

Обязательные аргументы: `url`, `token`.

### `local delete <task_id> [confirm]`

Обязательные аргументы: `task_id`.
Необязательные: `confirm`.

### `local recap [days_ago]`

Обязательных аргументов нет.
Необязательные: `days_ago`.

### `local screenshot <screenshot_id> [output]`

Обязательные аргументы: `screenshot_id`.
Необязательные: `output`.

### `local search <query> [include_completed]`

Обязательные аргументы: `query`.
Необязательные: `include_completed`.

### `local search-screen <query> [days] [app_filter] [limit]`

Обязательные аргументы: `query`.
Необязательные: `days`, `app_filter`, `limit`.

### `local sql <query>`

Обязательные аргументы: `query`.

### `local status`

Обязательных аргументов нет.

### `local tools`

Обязательных аргументов нет.
