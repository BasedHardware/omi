# Colocar tu historial de conversaciones en un calendario (.ics)

Usa esta receta para ver cuándo ocurrieron las conversaciones de Omi, junto a tus reuniones.
Lee una exportación JSON guardada, no realiza peticiones de red, no exporta transcripciones
y genera un único archivo iCalendar que Google Calendar, Apple Calendar, Outlook y Thunderbird
pueden importar. Cada conversación con un campo `started_at` se convierte en un evento que
abarca `started_at`–`finished_at` (30 minutos si `finished_at` está ausente). Necesitas Python 3.10+
y un `omi-cli` autenticado para la exportación inicial.

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo. Esta es una sola
página, no una copia de seguridad completa de la cuenta; para obtener otra página, incrementa
`--offset` en 200 y utiliza un nombre de archivo distinto.

Guarda el siguiente código como `conversations_to_ics.py`:

```python
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LENGTH = timedelta(minutes=30)


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
        raise ValueError("Expected the JSON array from omi --json conversation list")
    now = stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//omi-cli examples//conversations_to_ics//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Omi conversations"]
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        start = ics_datetime(item.get("started_at"))
        if start is None:
            skipped += 1
            continue
        end = ics_datetime(item.get("finished_at"))
        if end is None or end <= start:
            end = start + DEFAULT_LENGTH
        item_id = ics_text(item.get("id")) or "unknown"
        title = ics_text(structured.get("title")) or "(untitled conversation)"
        notes = [f"Omi conversation {item_id}"]
        for label, key in (("Category", "category"),):
            if structured.get(key):
                notes.append(f"{label}: {ics_text(structured.get(key))}")
        if item.get("source"):
            notes.append(f"Source: {ics_text(item.get('source'))}")
        lines += ["BEGIN:VEVENT", f"UID:omi-conversation-{item_id}@omi-cli", f"DTSTAMP:{now}",
                  f"DTSTART:{stamp(start)}", f"DTEND:{stamp(end)}", f"SUMMARY:{title}",
                  "DESCRIPTION:" + "\\n".join(notes), "STATUS:CONFIRMED", "CATEGORIES:Omi", "END:VEVENT"]
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
        sys.exit("Usage: python conversations_to_ics.py INPUT.json OUTPUT.ics")
    try:
        written, skipped = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} conversation(s) skipped (no start time)")
```

Ejecuta el conversor:

```sh
python conversations_to_ics.py conversations.json conversations.ics
```

Importa el archivo en tu aplicación de calendario (Google Calendar: Configuración → Importar y exportar;
Apple Calendar: Archivo → Importar; Outlook: Archivo → Abrir y exportar). Las horas se almacenan en UTC,
por lo que el calendario las muestra en tu zona horaria local. El UID del evento se deriva del ID de la
conversación, por lo que reimportar una exportación actualizada actualiza los mismos eventos en lugar de
duplicarlos en calendarios que respetan los UIDs. Las conversaciones sin hora de inicio se omiten y se
contabilizan. Los títulos que contienen comas, puntos y comas o saltos de línea se escapan debidamente,
las líneas largas se pliegan según el estándar RFC 5545, y el conversor se rehúsa a sobrescribir un
archivo existente. Trata el archivo exportado como información privada de conversación.
