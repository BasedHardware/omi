# Colocar tareas pendientes en tu calendario (.ics)

Usa esta receta para ver las tareas y elementos de acción pendientes de Omi junto
a tus reuniones. Lee una exportación JSON guardada, no realiza peticiones de red
y genera un único archivo iCalendar que Google Calendar, Apple Calendar, Outlook y
Thunderbird pueden importar. Únicamente los elementos con un campo `due_at` se convierten
en eventos; el conversor reporta cuántos no tenían fecha de vencimiento. Necesitas
Python 3.10+ y un `omi-cli` autenticado para la exportación inicial.

Exporta tus tareas pendientes (hasta 500):

```sh
omi --json action-item list --open --limit 500 > action_items.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo. Esta es una
sola página; para recuperar más, incrementa `--offset` en 500 y utiliza un nombre de archivo
distinto.

Guarda el siguiente código como `action_items_to_ics.py`:

```python
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_LENGTH = timedelta(minutes=30)


def ics_text(value):
    """Escapa texto para el valor de una propiedad iCalendar (RFC 5545 §3.3.11).

    La API de desarrollo tiene un tipado flexible, por lo que un campo puede llegar
    como un tipo no-string; cualquier valor no nulo se convierte a texto en lugar de
    rechazarse, para que una fila anómala no rompa el archivo.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_datetime(value):
    """Parsea una marca de tiempo ISO-8601 a un datetime UTC con zona horaria, o None si no es utilizable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line):
    """Pliega una línea de contenido a 75 octetos (RFC 5545 §3.1), sin dividir caracteres UTF-8."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts, chunk, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk, limit = b" " + b, 75
        else:
            chunk += b
    parts.append(chunk.decode("utf-8"))
    return parts


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    now = stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//omi-cli examples//action_items_to_ics//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Omi action items"]
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        due = ics_datetime(item.get("due_at"))
        if due is None:
            skipped += 1
            continue
        item_id = ics_text(item.get("id")) or "unknown"
        description = ics_text(item.get("description")) or "(no description)"
        notes = [f"Omi action item {item_id}"]
        if item.get("conversation_id"):
            notes.append(f"Conversation: {ics_text(item.get('conversation_id'))}")
        created = ics_datetime(item.get("created_at"))
        lines += ["BEGIN:VEVENT", f"UID:omi-action-{item_id}@omi-cli", f"DTSTAMP:{now}",
                  f"DTSTART:{stamp(due)}", f"DTEND:{stamp(due + EVENT_LENGTH)}",
                  f"SUMMARY:{description}", "DESCRIPTION:" + "\\n".join(notes),
                  "STATUS:" + ("COMPLETED" if item.get("completed") else "CONFIRMED"),
                  "CATEGORIES:Omi"]
        if created is not None:
            lines.append(f"CREATED:{stamp(created)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in fold(line)]
    payload = ("\r\n".join(folded) + "\r\n").encode("utf-8")
    output_path = Path(destination)
    # La creación exclusiva ('xb') protege contra la sobrescritura de una exportación existente; un fallo de escritura no deja archivos parciales.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(items) - skipped, skipped


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python action_items_to_ics.py INPUT.json OUTPUT.ics")
    try:
        written, skipped = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} item(s) skipped (no due date)")
```

Ejecuta el conversor:

```sh
python action_items_to_ics.py action_items.json action_items.ics
```

Importa el archivo en tu aplicación de calendario (Google Calendar: Configuración → Importar y exportar;
Apple Calendar: Archivo → Importar; Outlook: Archivo → Abrir y exportar). Cada elemento con fecha de
vencimiento se convierte en un evento de 30 minutos a partir de `due_at`, almacenado en UTC para que tu
calendario lo muestre en tu zona horaria local. El UID del evento se deriva del ID del elemento, por lo que
reimportar una exportación actualizada actualiza los mismos eventos en lugar de duplicarlos en calendarios
que respetan los UIDs. Los elementos sin fecha de vencimiento se omiten y se contabilizan. Las comas,
puntos y comas y saltos de línea en las descripciones se escapan debidamente, las líneas largas se pliegan
según RFC 5545, y el conversor se rehúsa a sobrescribir un archivo existente. Trata el archivo exportado
como datos privados.
