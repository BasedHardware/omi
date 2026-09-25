# Convertir tareas en un archivo todo.txt

Usa esta receta para mantener las tareas y elementos de acción de Omi en el formato
de texto plano [todo.txt](https://github.com/todotxt/todo.txt), compatible con el CLI
de todo.txt, Simpletask, sleek, Markor y muchas otras aplicaciones. Lee una exportación
JSON guardada, no realiza peticiones de red y escribe una tarea por línea: tareas abiertas
como texto plano, tareas completadas con el marcador `x` y un campo `due_at` como una
etiqueta `due:YYYY-MM-DD`. Necesitas Python 3.10+ y un `omi-cli` autenticado para la
exportación inicial.

Exporta hasta 500 tareas, tanto abiertas como completadas:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo. Esta es
una sola página; para recuperar más, incrementa `--offset` en 500 y utiliza un nombre de
archivo distinto. Añade `--open` para exportar únicamente los elementos pendientes de realizar.

Guarda el siguiente código como `action_items_to_todotxt.py` (el mismo script se encuentra
junto a esta receta como [`action_items_to_todotxt.py`](action_items_to_todotxt.py) y
está cubierto por `tests/test_action_items_to_todotxt.py`):

```python
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DONE_WORDS = {"true", "yes", "1", "done", "completed"}
RESERVED_KEYS = {"due", "t", "rec", "h", "pri", "omi"}
ZWSP = "​"  # espacio de ancho cero: interrumpe la sintaxis de todo.txt sin alterar el texto visual


def one_line(value):
    """Renderiza un campo exportado como texto de una sola línea.

    La API de desarrollo tiene un tipado flexible, por lo que un campo puede llegar
    como un tipo no-string; cualquier valor no nulo se convierte a texto en lugar de
    rechazarse, para que una fila anómala no rompa el archivo.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def task_text(value):
    """Evita que una descripción se interprete como sintaxis reservada de todo.txt."""
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word  # de lo contrario se interpretaría como un proyecto o contexto
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"  # de lo contrario sobrescribiría due:, omi:, ...
        words.append(word)
    text = " ".join(words) or "(no description)"
    if re.match(r"x |\([A-Z]\) |\d{4}-\d{2}-\d{2}( |$)", text):
        text = ZWSP + text  # de lo contrario se interpretaría como marca de completado, prioridad o fecha
    return text


def is_done(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return isinstance(value, str) and value.strip().lower() in DONE_WORDS


def parse_offset(text):
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    return timezone(delta if match.group(1) == "+" else -delta)


def local_date(value, zone):
    """Parsea una marca de tiempo ISO-8601 a la fecha del calendario local, o None si no es utilizable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone).date()


def task_line(done, due, item, zone):
    parts = []
    created = local_date(item.get("created_at"), zone)
    if done:
        parts.append("x")
        completed = local_date(item.get("completed_at"), zone)
        # todo.txt interpreta la primera fecha después de "x" como la fecha de completado,
        # por lo que la fecha de creación se escribe únicamente cuando le precede una fecha de completado.
        if completed is not None:
            parts.append(completed.isoformat())
            if created is not None:
                parts.append(created.isoformat())
    elif created is not None:
        parts.append(created.isoformat())
    parts.append(task_text(item.get("description")))
    if due is not None:
        parts.append(f"due:{due.isoformat()}")
    omi_id = one_line(item.get("id"))
    if omi_id and " " not in omi_id:
        parts.append(f"omi:{omi_id}")
    return " ".join(parts)


def convert(source, destination, zone):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    entries = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        entries.append((is_done(item.get("completed")), local_date(item.get("due_at"), zone), item))
    # Tareas abiertas primero, ordenadas por fecha de vencimiento más próxima; luego las tareas sin fecha.
    entries.sort(key=lambda e: (e[0], e[1] is None, e[1] or datetime.min.date()))
    lines = [task_line(done, due, item, zone) for done, due, item in entries]
    undated = sum(1 for _, due, _ in entries if due is None)
    # Genera el contenido completo antes de tocar el sistema de archivos,
    # para que un fallo de conversión no deje un archivo todo.txt truncado.
    payload = "".join(line + "\n" for line in lines).encode("utf-8")
    output_path = Path(destination)
    # La creación exclusiva ('xb') protege contra la sobrescritura de un archivo existente; un fallo de escritura no deja archivos parciales.
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
    return len(lines), undated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi action-item export to todo.txt.")
    parser.add_argument("source", help="JSON from omi --json action-item list")
    parser.add_argument("destination", help="new todo.txt file to create")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="use calendar dates at this offset (e.g. +09:00); default: this computer's time zone")
    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        written, undated = convert(args.source, args.destination, zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"todo.txt export failed: {exc}")
    print(f"{written} task(s) written, {undated} without a due date")
```

Ejecuta el conversor:

```sh
python action_items_to_todotxt.py action_items.json omi_todo.txt
```

Abre `omi_todo.txt` en cualquier aplicación compatible con todo.txt, o anéxalo al archivo
que ya utilices. Las tareas abiertas aparecen primero, ordenadas por fecha de vencimiento,
y las tareas sin fecha se conservan y contabilizan sin descartarse. Cada línea incluye la
fecha de creación, una etiqueta `due:` cuando el elemento tiene vencimiento y una etiqueta
`omi:` con el ID del elemento en Omi, para que puedas localizarlo nuevamente mediante
`omi action-item get`. Las tareas completadas inician con `x` y su fecha de finalización. Las
fechas de todo.txt no llevan zona horaria, por lo que corresponden a los días calendario en
la zona horaria de este equipo; pasa `--utc-offset +09:00` (por ejemplo) para seleccionar otro
desfase. Las descripciones se condensan a una sola línea, y las palabras que todo.txt interpretaría
como un proyecto (`+palabra`), un contexto (`@palabra`), una etiqueta de tipo `due:`/`omi:`,
una prioridad o una fecha se escapan con un espacio de ancho cero. Los campos con tipado flexible
se convierten en lugar de rechazarse, el conversor se rehúsa a sobrescribir un archivo existente
y una escritura fallida no deja archivos residuales. Trata el archivo exportado como datos privados.
