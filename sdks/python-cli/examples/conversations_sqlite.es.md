# Convertir una exportación de lista de conversaciones a una base de datos SQLite

Utiliza esta receta cuando desees consultar tus conversaciones de Omi con SQL: filtrar por categoría, buscar títulos o realizar combinaciones con elementos de acción. Lee una o más exportaciones JSON guardadas, no realiza solicitudes de red y complementa a [`conversations_csv.md`](conversations_csv.md) y [`conversations_xlsx.md`](conversations_xlsx.md).

Necesitas Python 3.10+ y un `omi-cli` autenticado para la exportación inicial. Los ejemplos de shell interactivo `python -m sqlite3` a continuación requieren Python 3.12+.

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando se haya ejecutado correctamente antes de importar. Esto representa una página, no una copia de seguridad completa de la cuenta. Para obtener otra página, incrementa `--offset` en 200 y utiliza un nombre de archivo diferente. Los cambios en la cuenta entre solicitudes pueden afectar la paginación por desplazamiento; esta receta no promete una instantánea coherente.

Ejecuta el importador:

```sh
python sdks/python-cli/examples/conversations_to_sqlite.py conversations.json -o conversations.db
```

Se pueden fusionar múltiples páginas en una sola ejecución:

```sh
python sdks/python-cli/examples/conversations_to_sqlite.py \
  page1.json page2.json page3.json -o conversations.db
```

Volver a ejecutar con las mismas exportaciones o con exportaciones actualizadas es seguro: el importador utiliza `INSERT OR REPLACE` basado en `id`, por lo que las filas se actualizan en lugar de duplicarse.

## Esquema

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    category      TEXT,
    source        TEXT,
    started_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    created_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    updated_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    transcript    TEXT,
    raw_json      TEXT NOT NULL
);
```

Todas las marcas de tiempo se normalizan a texto UTC `YYYY-MM-DD HH:MM:SS` para que las funciones de fecha y hora de SQLite (`strftime`, `julianday`, `date`) funcionen sin necesidad de coerción. El registro original se mantiene intacto en `raw_json` para consultas con `json_extract`.

## Consultas de ejemplo

```sh
python -m sqlite3 conversations.db
```

Contar conversaciones por categoría:

```sql
SELECT category, COUNT(*) AS n
FROM conversations
GROUP BY category
ORDER BY n DESC;
```

Buscar conversaciones de los últimos 7 días:

```sql
SELECT title, started_at
FROM conversations
WHERE started_at >= date('now', '-7 days')
ORDER BY started_at DESC;
```

Extraer un campo anidado del JSON sin procesar (por ejemplo, emoji):

```sql
SELECT title, json_extract(raw_json, '$.structured.emoji') AS emoji
FROM conversations
LIMIT 10;
```

Buscar en los títulos:

```sql
SELECT id, title, category, started_at
FROM conversations
WHERE title LIKE '%meeting%'
ORDER BY started_at DESC;
```

Trata el archivo exportado como datos privados de conversaciones. La base de datos SQLite contiene la misma información que el JSON de origen. Para obtener valores exactos sin modificar, conserva el JSON de origen junto a la base de datos.
