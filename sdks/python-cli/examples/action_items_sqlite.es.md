# Convertir una exportación de elementos de acción a SQLite

Utiliza esta receta para almacenar, consultar y buscar tus tareas y elementos de acción de Omi en una base de datos SQLite local. Lee exportaciones JSON guardadas, no realiza solicitudes de red y normaliza las marcas de tiempo a texto UTC para que las funciones de fecha y hora de SQLite funcionen a la perfección. Necesitas Python 3.10+ y un `omi-cli` autenticado para la exportación inicial.

Exporta hasta 200 elementos de acción:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

Verifica que el comando se haya ejecutado correctamente antes de convertir el archivo. Esto representa una página, no una copia de seguridad completa de la cuenta. Para obtener otra página, incrementa `--offset` en 200 y utiliza un nombre de archivo diferente. Los cambios en la cuenta entre solicitudes pueden afectar la paginación por desplazamiento; esta receta no promete una instantánea coherente.

Guarda lo siguiente como `action_items_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    completed INTEGER NOT NULL,
    due_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    conversation_id TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS action_items_completed ON action_items (completed);
CREATE INDEX IF NOT EXISTS action_items_created_at ON action_items (created_at);
CREATE INDEX IF NOT EXISTS action_items_conversation_id ON action_items (conversation_id);
"""


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def utc_stamp(value):
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' so SQLite date functions work."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def boolean_to_int(value):
    """Normalize completed status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return 0


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("action_items")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing action items")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each action item must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: action item is missing an id")
        description = item.get("description") or item.get("title") or ""
        rows.append((
            str(item_id),
            text(description),
            boolean_to_int(item.get("completed")),
            utc_stamp(item.get("due_at")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            text(item.get("conversation_id")),
            json.dumps(item, ensure_ascii=False)
        ))
    return rows


def load(database, sources):
    """Load action items from one or more JSON exports into a SQLite database."""
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO action_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python action_items_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} action item(s) in database")
```

Carga las páginas exportadas (repite con nuevas exportaciones en cualquier momento):

```sh
python action_items_to_sqlite.py tasks.sqlite action_items_0.json action_items_200.json
```

Consulta la base de datos. Contar tareas pendientes vs completadas:

```sh
python -m sqlite3 tasks.sqlite "SELECT CASE completed WHEN 1 THEN 'completed' ELSE 'open' END AS status, COUNT(*) AS count FROM action_items GROUP BY completed"
```

Buscar tareas pendientes, las más recientes primero:

```sh
python -m sqlite3 tasks.sqlite "SELECT id, description, created_at FROM action_items WHERE completed = 0 ORDER BY created_at DESC"
```

Buscar tareas por palabra clave:

```sh
python -m sqlite3 tasks.sqlite "SELECT description, completed FROM action_items WHERE description LIKE '%review%' ORDER BY created_at DESC"
```

`created_at`, `updated_at` y `due_at` se almacenan como texto UTC `YYYY-MM-DD HH:MM:SS`, por lo que se ordenan cronológicamente y funcionan con las funciones `date()`, `datetime()` y `strftime()` de SQLite. `completed` se almacena como `0` o `1` con un índice para un filtrado rápido por estado. Cada objeto original se preserva íntegramente en `raw_json` para su uso con `json_extract`. El cargador valida cada archivo de entrada antes de escribir, aplica cada ejecución como una sola transacción y reemplaza las filas que comparten un `id`, por lo que cargar la misma página dos veces deja exactamente una fila por elemento de acción.
