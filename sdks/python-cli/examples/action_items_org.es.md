# Convertir tareas en un archivo de agenda Org-mode

Usa esta receta para gestionar las tareas y elementos de acción de Omi en Emacs Org mode,
o en una aplicación compatible como Orgzly o beorg. Lee una exportación JSON guardada, no
realiza peticiones de red y escribe un único archivo `.org`: cada tarea se convierte en un
encabezado `TODO` o `DONE`, y un campo `due_at` se transforma en un `DEADLINE`, de modo que
los elementos aparecen en tu agenda Org junto al resto de tus compromisos. Necesitas
Python 3.10+ y un `omi-cli` autenticado para la exportación inicial.

Exporta hasta 500 tareas, tanto abiertas como completadas:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo. Esta es
una sola página; para recuperar más, incrementa `--offset` en 500 y utiliza un nombre de
archivo distinto. Añade `--open` para exportar únicamente los elementos pendientes de realizar.

Guarda el siguiente código como `action_items_to_org.py` (el mismo script se encuentra
junto a esta receta como [`action_items_to_org.py`](action_items_to_org.py) y está cubierto
por `tests/test_action_items_to_org.py`):

```python
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DONE_WORDS = {"true", "yes", "1", "done", "completed"}
ZWSP = "​"  # espacio de ancho cero, carácter de escape documentado en Org


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


def heading_text(value):
    """Evita que una descripción se interprete como sintaxis de Org dentro de un encabezado."""
    text = one_line(value) or "(no description)"
    if text.startswith("[#"):
        text = ZWSP + text  # de lo contrario se convertiría en un indicador de prioridad
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # evita marcas de tiempo erróneas en agenda
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # de lo contrario se convertiría en etiquetas de encabezado
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


def local_time(value, zone):
    """Parsea una marca de tiempo ISO-8601 a la hora local de reloj, o None si no es utilizable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def org_stamp(dt, active):
    body = f"{dt:%Y-%m-%d} {WEEKDAYS[dt.weekday()]} {dt:%H:%M}"
    return f"<{body}>" if active else f"[{body}]"


def convert(source, destination, zone):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    entries = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        done = is_done(item.get("completed"))
        due = local_time(item.get("due_at"), zone)
        entries.append((done, due, item))
    # Tareas abiertas primero, fecha límite más próxima primero; luego las tareas sin fecha límite.
    entries.sort(key=lambda e: (e[0], e[1] is None, e[1].timestamp() if e[1] else 0.0))
    lines = ["# -*- mode: org; coding: utf-8 -*-", "#+TITLE: Omi action items", ""]
    undated = 0
    for done, due, item in entries:
        lines.append(f"* {'DONE' if done else 'TODO'} {heading_text(item.get('description'))}")
        planning = []
        closed = local_time(item.get("completed_at"), zone) if done else None
        if closed is not None:
            planning.append("CLOSED: " + org_stamp(closed, active=False))
        if due is not None:
            planning.append("DEADLINE: " + org_stamp(due, active=True))
        else:
            undated += 1
        if planning:
            lines.append(" ".join(planning))
        lines.append(":PROPERTIES:")
        for key, value in (("OMI_ID", one_line(item.get("id"))),
                           ("CONVERSATION", one_line(item.get("conversation_id")))):
            if value:
                lines.append(f":{key}: {value}")
        created = local_time(item.get("created_at"), zone)
        if created is not None:
            lines.append(":CREATED: " + org_stamp(created, active=False))
        lines.append(":END:")
    # Construye el archivo completo antes de tocar el sistema de archivos,
    # para que un fallo de conversión no deje un archivo .org truncado.
    payload = ("\n".join(lines) + "\n").encode("utf-8")
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
    return len(entries), undated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi action-item export to an Org file.")
    parser.add_argument("source", help="JSON from omi --json action-item list")
    parser.add_argument("destination", help="new .org file to create")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="write times at this offset (e.g. +09:00); default: this computer's time zone")
    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        written, undated = convert(args.source, args.destination, zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"Org export failed: {exc}")
    print(f"{written} heading(s) written, {undated} without a deadline")
```

Ejecuta el conversor:

```sh
python action_items_to_org.py action_items.json omi_action_items.org
```

Añade el archivo a `org-agenda-files` (o ábrelo en Orgzly o beorg) y los elementos con fecha
de vencimiento aparecerán en la agenda en su respectiva fecha límite. Las tareas abiertas aparecen
primero, ordenadas por fecha límite; las tareas sin fecha de vencimiento se conservan como
encabezados `TODO` estándar y se contabilizan sin descartarse. Las tareas completadas se convierten
en `DONE`, con una marca de tiempo `CLOSED` cuando `completed_at` está presente. El ID del elemento
en Omi, el ID de la conversación de origen y la hora de creación se conservan en el cajón de propiedades
(`:PROPERTIES:`) de cada encabezado, permitiendo localizar el elemento nuevamente con `omi action-item get`.
Las marcas de tiempo de Org no tienen zona horaria, por lo que se escriben en la hora local de este equipo;
pasa `--utc-offset +09:00` (por ejemplo) para seleccionar otro desfase. Las descripciones se condensan a
una sola línea, y el texto que Org interpretaría como prioridad, etiquetas o marcas de tiempo de agenda
se escapa con un espacio de ancho cero. Los campos con tipado flexible se convierten en lugar de rechazarse,
el conversor se rehúsa a sobrescribir un archivo existente y una escritura fallida no deja archivos residuales.
Trata el archivo exportado como información privada.
