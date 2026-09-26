# Generar un reporte HTML autocontenido de tus conversaciones

Utiliza esta receta para explorar o imprimir un período de conversaciones de Omi sin necesidad del
CLI ni de una hoja de cálculo: convierte una o más exportaciones de `conversation list` en un
único archivo HTML con una línea de resumen, una sección por día y una tabla con las
conversaciones grabadas ese día (hora de inicio, duración, título, categoría, carpeta,
origen, idioma, ID). Lee exportaciones JSON guardadas, no realiza peticiones de red,
no exporta transcripciones y genera un archivo HTML sin scripts, hojas de estilo externas
ni imágenes. Necesitas Python 3.10+ y un `omi-cli` autenticado para
la exportación inicial.

Exporta el período que deseas reportar (200 conversaciones por página):

```sh
omi --json conversation list --limit 200 --offset 0 --start-date 2026-09-14T00:00:00Z --end-date 2026-09-21T00:00:00Z > week.json
```

Verifica que el comando se ejecutó con éxito antes de convertir el archivo. Si una página está
llena, obtén la siguiente con `--offset 200` en un segundo archivo; el reporte
admite múltiples archivos y lista cada ID de conversación una sola vez.

Guarda lo siguiente como `conversations_html.py`:

```python
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

COLUMNS = ("Inicio", "Duración", "Título", "Categoría", "Carpeta", "Origen", "Idioma", "ID")

STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; color: #1a1a1a; background: #fff; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ccc; }
p.summary { color: #444; } table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; vertical-align: top; }
th { background: #f3f3f3; } td.num { text-align: right; white-space: nowrap; } td.id { font-family: monospace; font-size: 0.8rem; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } tr { page-break-inside: avoid; } }
"""


def text(value):
    """Representa un campo como una línea de texto; cualquier valor no nulo se convierte, no se rechaza."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def parse_time(value):
    """Convierte una marca de tiempo ISO-8601 en un datetime UTC consciente, o None si no es válida."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value):
    """Convierte '+09:00' / '-05:30' en un timedelta para días de calendario y horarios locales."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"El desfase UTC debe tener el formato +09:00, se recibió {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"El desfase UTC debe estar entre -14:00 y +14:00, se recibió {value!r}")
    return -delta if value[0] == "-" else delta


def load(sources):
    conversations = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: se esperaba el arreglo JSON de omi --json conversation list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: cada conversación debe ser un objeto")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: cada conversación requiere un id de tipo cadena")
            structured = item.get("structured")
            if structured is None:
                structured = {}
            if not isinstance(structured, dict):
                raise ValueError(f"{source}: el campo structured de la conversación debe ser un objeto o null")
            conversations[item_id] = item
    return conversations


def rows_by_day(conversations, offset):
    """Agrupa conversaciones en días calendario locales; retorna (days, undated) ordenados por inicio."""
    days, undated = defaultdict(list), []
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        structured = item.get("structured") or {}
        seconds = int((end - start).total_seconds()) if start is not None and end is not None and end >= start else 0
        row = {
            "start": (start + offset).strftime("%H:%M") if start is not None else "",
            "sort": start if start is not None else datetime.max.replace(tzinfo=timezone.utc),
            "seconds": seconds,
            "title": text(structured.get("title")) or "(conversación sin título)",
            "category": text(structured.get("category")),
            "folder": text(item.get("folder_name")),
            "source": text(item.get("source")),
            "language": text(item.get("language")),
            "id": item_id,
        }
        if start is None:
            undated.append(row)
        else:
            days[(start + offset).strftime("%Y-%m-%d")].append(row)
    for bucket in list(days.values()) + [undated]:
        bucket.sort(key=lambda row: (row["sort"], row["id"]))
    return dict(sorted(days.items())), undated


def minutes(seconds):
    return f"{seconds / 60:.0f} min"


def table(rows):
    lines = ["<table>", "<thead><tr>" + "".join(f"<th>{escape(column)}</th>" for column in COLUMNS) + "</tr></thead>", "<tbody>"]
    for row in rows:
        cells = [
            f"<td class=\"num\">{escape(row['start'])}</td>",
            f"<td class=\"num\">{escape(minutes(row['seconds']))}</td>",
            f"<td>{escape(row['title'])}</td>",
            f"<td>{escape(row['category'])}</td>",
            f"<td>{escape(row['folder'])}</td>",
            f"<td>{escape(row['source'])}</td>",
            f"<td>{escape(row['language'])}</td>",
            f"<td class=\"id\">{escape(row['id'])}</td>",
        ]
        lines.append("<tr>" + "".join(cells) + "</tr>")
    lines += ["</tbody>", "</table>"]
    return "\n".join(lines)


def report(conversations, offset, offset_label):
    days, undated = rows_by_day(conversations, offset)
    total = sum(len(rows) for rows in days.values())
    total_seconds = sum(row["seconds"] for rows in days.values() for row in rows)
    summary = f"Conversaciones: {total} · Tiempo grabado: {total_seconds / 3600:.1f} h · Días con grabaciones: {len(days)}"
    if undated:
        summary += f" · Sin fecha: {len(undated)}"
    parts = ["<!DOCTYPE html>", "<html lang=\"es\">", "<head>", "<meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
             "<title>Reporte de conversaciones de Omi</title>", f"<style>{STYLE}</style>", "</head>", "<body>",
             "<h1>Reporte de conversaciones de Omi</h1>",
             f"<p class=\"summary\">{escape(summary)}<br>Horas mostradas en UTC{escape(offset_label)}.</p>"]
    if not days and not undated:
        parts.append("<p>No hay conversaciones en la exportación.</p>")
    for day, rows in days.items():
        day_seconds = sum(row["seconds"] for row in rows)
        parts += [f"<h2 id=\"d{escape(day)}\">{escape(day)}</h2>",
                  f"<p class=\"summary\">{len(rows)} conversación{'es' if len(rows) != 1 else ''} · {day_seconds / 3600:.1f} h</p>",
                  table(rows)]
    if undated:
        parts += ["<h2 id=\"undated\">Sin fecha</h2>",
                  f"<p class=\"summary\">{len(undated)} conversación{'es' if len(undated) != 1 else ''} sin hora de inicio</p>",
                  table(undated)]
    parts += ["</body>", "</html>"]
    return "\n".join(parts) + "\n"


def convert(sources, destination, offset, offset_label):
    payload = report(load(sources), offset, offset_label).encode("utf-8")
    output_path = Path(destination)
    # La creación exclusiva protege un reporte existente; una escritura fallida no deja un archivo parcial.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Se rechaza sobrescribir el archivo existente {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    args = sys.argv[1:]
    offset, offset_label = timedelta(0), ""
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            offset = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"Falló la generación del reporte: {exc}")
        offset_label = args[1]
        args = args[2:]
    if len(args) < 2:
        sys.exit("Uso: python conversations_html.py [--utc-offset +09:00] SALIDA.html ENTRADA.json [ENTRADA.json ...]")
    try:
        convert(args[1:], args[0], offset, offset_label)
    except (OSError, ValueError) as exc:
        sys.exit(f"Falló la generación del reporte: {exc}")
    print(f"reporte guardado en {args[0]}")
```

Ejecútalo (el archivo de salida va primero, seguido de una o más exportaciones):

```sh
python conversations_html.py --utc-offset +09:00 week.html week.json
```

Abre `week.html` en cualquier navegador; también se imprime limpiamente, un día por encabezado.
La línea de resumen contabiliza conversaciones, horas grabadas y días; la sección de cada día
lista las conversaciones de esa jornada en orden de inicio con su duración
(`finished_at − started_at`, `0 min` si falta el final o es anterior al
inicio), título, categoría, carpeta, origen, idioma e ID. Los días y las horas
utilizan la zona horaria indicada mediante `--utc-offset`; omítelo para usar UTC. Las
conversaciones sin una hora de inicio utilizable se listan en una sección "Sin fecha" al
final. Los títulos y las categorías provienen del objeto `structured` que retorna la API,
por lo que no se lee ni escribe texto de transcripciones, y cada valor se
escapa en HTML, garantizando que un título con `<` o `&` se muestre de forma literal en vez de ser
interpretado. El script rechaza sobrescribir un reporte existente, por lo que se recomienda usar un
archivo por período. Trata el archivo generado como información privada.
