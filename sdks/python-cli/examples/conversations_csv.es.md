# Convertir una exportación de conversaciones a CSV

Usa esta receta para revisar los metadatos de las conversaciones en una hoja
de cálculo. Lee un archivo JSON guardado, no hace solicitudes de red y no
exporta transcripciones. Necesitas Python 3.10 o posterior y un `omi-cli`
autenticado para realizar la exportación inicial.

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Comprueba que el comando terminó correctamente antes de convertir el archivo.
Esta es una sola página, no una copia de seguridad completa de la cuenta. Para
obtener otra página, aumenta `--offset` en 200 y usa un nombre de archivo
distinto. Los cambios en la cuenta entre solicitudes pueden afectar la
paginación por desplazamiento; esta receta no promete una instantánea
consistente.

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

Importa el resultado como texto UTF-8 delimitado por comas en Excel u otra
aplicación de hojas de cálculo. El conversor conserva los IDs completos, los
acentos, el texto entre comillas y los saltos de línea internos. Los campos
ausentes se convierten en celdas vacías; una lista vacía produce solo la fila
de encabezados. Se niega a sobrescribir un destino existente y una escritura
fallida no deja una exportación parcial. Trata el archivo exportado como datos
privados de conversaciones. Para conservar valores exactamente sin modificar,
guarda el JSON de origen; el CSV añade un apóstrofo a los valores comunes que
parecen fórmulas para que se interpreten explícitamente como texto.
