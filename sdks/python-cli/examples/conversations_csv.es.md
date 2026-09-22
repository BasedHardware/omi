# Convertir una exportación de lista de conversaciones a CSV

Utiliza esta receta para revisar los metadatos de tus conversaciones en una hoja de cálculo. Lee una exportación JSON guardada, no realiza solicitudes de red y no exporta transcripciones. Necesitas Python 3.10+ y un `omi-cli` autenticado para la exportación inicial.

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando se haya ejecutado correctamente antes de convertir el archivo. Esto representa una página, no una copia de seguridad completa de la cuenta. Para obtener otra página, incrementa `--offset` en 200 y utiliza un nombre de archivo diferente. Los cambios en la cuenta entre solicitudes pueden afectar la paginación por desplazamiento; esta receta no promete una instantánea coherente.

Guarda lo siguiente como `conversations_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "title", "category", "started_at", "source")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        values = (item.get("id"), structured.get("title"), structured.get("category"),
                  item.get("started_at"), item.get("source"))
        rows.append([spreadsheet_text(value) for value in values])
    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # Exclusive creation still protects an existing export.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # Leave no partial export behind when the write itself fails.
        output_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python conversations_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
```

Ejecuta el conversor:

```sh
python conversations_to_csv.py conversations.json conversations.csv
```

Abre `conversations.csv` en Excel, LibreOffice Calc o Google Sheets. Las columnas son:

* `id` - identificador único de la conversación en Omi.
* `title` - título generado automáticamente o editado por el usuario.
* `category` - categoría de la conversación (por ejemplo, `work`, `casual`).
* `started_at` - marca de tiempo ISO-8601 del inicio de la conversación.
* `source` - dispositivo o cliente de origen (por ejemplo, `omi_necklace`).

Trata el archivo exportado como datos privados de conversaciones. El archivo CSV contiene identificadores y metadatos de conversaciones que no deben compartirse públicamente sin revisión previa.
