# Convertir una exportación de lista de conversaciones a un libro de Excel (.xlsx)

Usa esta receta cuando desees tener la lista de conversaciones en Excel con tipos
de celda reales: `started_at` / `finished_at` se convierten en celdas datetime que
puedes ordenar y filtrar, se calcula una columna `duration_min` automáticamente,
la fila de encabezados se congela y se habilita el Autofiltro. Lee una exportación
JSON guardada, no realiza peticiones de red y no exporta transcripciones.
Complementa a [`conversations_csv.md`](conversations_csv.md), que se mantiene sin
dependencias externas; esta receta requiere un paquete adicional.

Necesitas Python 3.10+, un `omi-cli` autenticado para la exportación inicial y
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo.
Esta es una sola página, no una copia de seguridad completa de la cuenta. Para
obtener otra página, incrementa `--offset` en 200 y utiliza un nombre de archivo
distinto. Los cambios en la cuenta entre peticiones pueden afectar la paginación
por desplazamiento (offset); esta receta no garantiza una instantánea consistente.

Guarda el siguiente código como `conversations_to_xlsx.py`:

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
    """Renderiza un campo exportado como texto.

    La API de desarrollo tiene un tipado flexible, por lo que un campo puede llegar
    como un tipo no-string aunque el CLI lo modele como Optional[str]. Una fila anómala
    no debe destruir una exportación completa, por lo que cualquier valor no nulo se
    convierte a texto en lugar de rechazarse.
    Las celdas se escriben con un tipo explícito de cadena, por lo que un valor como
    "=SUM(A1)" se mantiene como texto y nunca se evalúa como una fórmula.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_datetime(value):
    """Convierte una marca de tiempo ISO-8601 en un datetime UTC naive para Excel.

    Las celdas de Excel no pueden contener zona horaria, por lo que cada desfase se
    convierte a UTC y el encabezado lo indica explícitamente. Cualquier valor que no sea
    una marca de tiempo interpretable se conserva como texto en lugar de descartarse.
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
    # Escribe junto al destino y renombra atómicamente, para que un fallo al guardar
    # no deje un libro de trabajo truncado para la siguiente ejecución.
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

Abre el libro en Excel, LibreOffice o Google Sheets. Las marcas de tiempo son celdas
datetime reales en UTC (el encabezado así lo especifica), `duration_min` es numérico
y todas las demás columnas son texto, de modo que los IDs conservan ceros iniciales y
un título que asemeje una fórmula nunca es evaluado como tal. Los campos ausentes se
convierten en celdas vacías; una lista vacía genera únicamente la fila de encabezados.
El conversor se rehúsa a sobrescribir un destino existente, y un fallo al guardar no
deja ningún archivo parcial residual. Trata el archivo exportado como datos privados
de conversación. Para conservar los valores originales exactos sin modificar, guarda el
JSON de origen.
