# Convertir una exportación de lista de conversaciones a un libro de Excel (.xlsx)

Utiliza esta receta cuando desees la lista de conversaciones en Excel con tipos de celdas reales: `started_at` / `finished_at` se convierten en celdas de fecha y hora que puedes ordenar y filtrar, se calcula automáticamente una columna `duration_min`, la fila de encabezado se bloquea y se habilita el filtro automático (AutoFilter). Lee una exportación JSON guardada, no realiza solicitudes de red y no exporta transcripciones. Complementa a [`conversations_csv.md`](conversations_csv.md), que no requiere dependencias; esta receta necesita un paquete adicional.

Necesitas Python 3.10+, un `omi-cli` autenticado para la exportación inicial y [`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando se haya ejecutado correctamente antes de convertir el archivo. Esto representa una página, no una copia de seguridad completa de la cuenta. Para obtener otra página, incrementa `--offset` en 200 y utiliza un nombre de archivo diferente. Los cambios en la cuenta entre solicitudes pueden afectar la paginación por desplazamiento; esta receta no promete una instantánea coherente.

Guarda lo siguiente como `conversations_to_xlsx.py`:

```python
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

FIELDS = ("id", "title", "category", "started_at", "finished_at", "duration_min", "source")
DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"


def cell_text(value):
    """Render one exported field as text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    Cells are written with an explicit string type, so a value such as
    "=SUM(A1)" stays text and is never evaluated as a formula.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_datetime(value):
    """Parse an ISO-8601 timestamp into a naive UTC datetime for Excel.

    Excel cells cannot carry a timezone, so every offset is converted to UTC
    and the header says so. Anything that is not a parseable timestamp is
    kept as text instead of being dropped.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return cell_text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "conversations"
    header = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        started = cell_datetime(item.get("started_at"))
        finished = cell_datetime(item.get("finished_at"))
        duration = None
        if isinstance(started, datetime) and isinstance(finished, datetime):
            duration = round((finished - started).total_seconds() / 60, 1)
        row = (
            cell_text(item.get("id")),
            cell_text(structured.get("title")),
            cell_text(structured.get("category")),
            started,
            finished,
            duration,
            cell_text(item.get("source")),
        )
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = DATETIME_FORMAT
            elif isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, name in enumerate(FIELDS, start=1):
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in sheet[get_column_letter(index)])
        sheet.column_dimensions[get_column_letter(index)].width = min(max(len(name), longest) + 2, 60)

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")
    # Write next to the destination and rename, so a failed save cannot leave a
    # truncated workbook behind for the next run.
    partial = output_path.with_name(output_path.name + ".partial")
    try:
        workbook.save(partial)
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python conversations_to_xlsx.py INPUT.json OUTPUT.xlsx")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"XLSX export failed: {exc}")
```

Ejecuta el conversor:

```sh
python conversations_to_xlsx.py conversations.json conversations.xlsx
```

Abre el libro en Excel, LibreOffice o Google Sheets. Las marcas de tiempo son celdas reales de fecha y hora en UTC (como indica el encabezado), `duration_min` es un número, y cada una de las demás columnas es texto, por lo que los identificadores conservan los ceros iniciales y un título que parece una fórmula nunca se evalúa. Los campos ausentes se convierten en celdas vacías; una lista vacía produce únicamente la fila de encabezado. El conversor se niega a sobrescribir un destino existente, y un error al guardar no deja ningún archivo parcial. Trata el archivo exportado como datos privados de conversaciones. Para obtener valores exactos sin modificar, conserva el JSON de origen.
