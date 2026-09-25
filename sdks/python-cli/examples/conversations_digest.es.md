# Generar un resumen de conversaciones (totales diarios, categorías, sesiones más largas)

Usa esta receta para ver cuánto grabó Omi y de qué trató, sin necesidad de leer
las transcripciones: transforma una o más exportaciones de `conversation list` en un
resumen breve en Markdown con totales por día, desglose por categoría y las conversaciones
más largas. Lee exportaciones JSON guardadas, no realiza peticiones de red, no exporta
transcripciones y genera un único archivo Markdown. Necesitas Python 3.10+ y un
`omi-cli` autenticado para la exportación inicial.

Exporta el periodo que deseas resumir (200 conversaciones por página):

```sh
omi --json conversation list --limit 200 --offset 0 --start-date 2026-09-14T00:00:00Z --end-date 2026-09-21T00:00:00Z > week.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo. Si una
página está completa, recupera la siguiente con `--offset 200` en un segundo archivo; el
resumen acepta múltiples archivos y cuenta cada identificador de conversación una sola vez.

Guarda el siguiente código como `conversations_digest.py`:

```python
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def text(value):
    """Renderiza un campo con tipado flexible como una sola línea de texto; cualquier valor no nulo se convierte, no se rechaza."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def parse_time(value):
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


def parse_offset(value):
    """Convierte '+09:00' / '-05:30' en un timedelta para días del calendario local."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    return -delta if value[0] == "-" else delta


def load(sources):
    conversations = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: expected the JSON array from omi --json conversation list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each conversation must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: each conversation needs a string id")
            structured = item.get("structured")
            if structured is None:
                structured = {}
            if not isinstance(structured, dict):
                raise ValueError(f"{source}: conversation structured field must be an object or null")
            conversations[item_id] = item
    return conversations


def hours(seconds):
    return f"{seconds / 3600:.1f}"


def digest(conversations, offset):
    per_day = defaultdict(lambda: [0, 0])          # day -> [count, seconds]
    per_category = defaultdict(lambda: [0, 0])
    longest, undated = [], 0
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        if start is None:
            undated += 1
            continue
        seconds = int((end - start).total_seconds()) if end is not None and end >= start else 0
        structured = item.get("structured") or {}
        day = (start + offset).strftime("%Y-%m-%d")
        category = text(structured.get("category")) or "(uncategorised)"
        for bucket in (per_day[day], per_category[category]):
            bucket[0] += 1
            bucket[1] += seconds
        longest.append((seconds, day, text(structured.get("title")) or "(untitled conversation)", item_id))
    total = sum(count for count, _ in per_day.values())
    total_seconds = sum(seconds for _, seconds in per_day.values())
    lines = ["# Omi conversation digest", "",
             f"Conversations: {total} · Recorded time: {hours(total_seconds)} h · Days with recordings: {len(per_day)}"]
    if undated:
        lines.append(f"Skipped (no start time): {undated}")
    lines += ["", "## Per day", "", "| Day | Conversations | Hours |", "|---|---:|---:|"]
    lines += [f"| {day} | {count} | {hours(seconds)} |" for day, (count, seconds) in sorted(per_day.items())]
    lines += ["", "## Per category", "", "| Category | Conversations | Hours |", "|---|---:|---:|"]
    by_category = sorted(per_category.items(), key=lambda entry: (-entry[1][0], entry[0]))
    lines += [f"| {category} | {count} | {hours(seconds)} |" for category, (count, seconds) in by_category]
    lines += ["", "## Longest conversations", ""]
    top = sorted(longest, key=lambda entry: (-entry[0], entry[1], entry[3]))[:5]
    lines += [f"- {hours(seconds)} h · {day} · {title} `{item_id}`" for seconds, day, title, item_id in top] or ["_None._"]
    return "\n".join(lines) + "\n"


def convert(sources, destination, offset):
    payload = digest(load(sources), offset).encode("utf-8")
    output_path = Path(destination)
    # La creación exclusiva ('xb') protege contra la sobrescritura de un resumen existente; un fallo de escritura no deja archivos parciales.
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


if __name__ == "__main__":
    args = sys.argv[1:]
    offset = timedelta(0)
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            offset = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"Digest failed: {exc}")
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python conversations_digest.py [--utc-offset +09:00] OUTPUT.md INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], offset)
    except (OSError, ValueError) as exc:
        sys.exit(f"Digest failed: {exc}")
    print(f"digest written to {args[0]}")
```

Ejecútalo (el archivo de destino va primero, seguido de una o más exportaciones):

```sh
python conversations_digest.py --utc-offset +09:00 week_digest.md week.json
```

El resumen consta de tres partes: una tabla por día (conversaciones y horas grabadas),
una tabla por categoría ordenada por cantidad, y las cinco conversaciones más largas con
sus respectivos identificadores. Los días corresponden a días calendario en la zona horaria
proporcionada mediante `--utc-offset`; si se omite, se agrupan por UTC. El tiempo grabado
es `finished_at − started_at`; una conversación sin hora de inicio válida se contabiliza en
"Skipped", y una sin hora de finalización (o con fin anterior al inicio) cuenta como 0 h
pero sigue sumando como conversación. Las categorías y títulos provienen del objeto
`structured` devuelto por la API, por lo que no se lee ni escribe texto de transcripción.
El script se rehúsa a sobrescribir un resumen existente, por lo que se recomienda un
archivo por periodo. Trata el archivo como información privada.
