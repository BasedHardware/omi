# Convertir una exportación de lista de conversaciones a CSV

Usa esta receta para revisar los metadatos de las conversaciones en una hoja de cálculo.
Lee una exportación JSON guardada, no realiza peticiones de red y no exporta transcripciones.
Necesitas Python 3.10+ y un `omi-cli` autenticado para la exportación inicial.

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando haya finalizado con éxito antes de convertir el archivo.
Esta es una sola página, no una copia de seguridad completa de la cuenta. Para
obtener otra página, incrementa `--offset` en 200 y utiliza un nombre de archivo
distinto. Los cambios en la cuenta entre peticiones pueden afectar la paginación
por desplazamiento (offset); esta receta no garantiza una instantánea consistente.

Guarda el siguiente código como `conversations_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "title", "category", "started_at", "source")


def spreadsheet_text(value):
    """Renderiza un campo exportado como texto seguro para hojas de cálculo.

    La API de desarrollo tiene un tipado flexible, por lo que un campo puede llegar
    como un tipo no-string aunque el CLI lo modele como Optional[str]. Una fila anómala
    no debe destruir una exportación completa, por lo que cualquier valor no nulo se
    convierte a texto en lugar de rechazarse.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Evita que los prefijos comunes de fórmula se interpreten como tales al importar.
    # El apóstrofo es intencional y puede ser visible en algunos importadores.
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
    # Formatea y codifica toda la exportación antes de tocar el sistema de archivos,
    # para que un fallo de conversión no deje un archivo CSV truncado para la siguiente ejecución.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # La creación exclusiva ('xb') protege contra la sobrescritura de una exportación existente.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # No deja ninguna exportación parcial residual si falla la escritura.
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

Importa el resultado como texto delimitado por comas y codificado en UTF-8 en Excel u otra
aplicación de hoja de cálculo. El conversor preserva identificadores completos, acentos, texto
entre comillas y saltos de línea incrustados. Los campos ausentes se convierten en celdas vacías;
una lista vacía genera únicamente la fila de encabezados. El conversor se rehúsa a sobrescribir
un destino existente, y una escritura fallida no deja ningún archivo parcial residual. Trata el
archivo exportado como datos privados de conversación. Para conservar los valores originales
exactos sin modificar, guarda el JSON fuente; el archivo CSV añade un apóstrofo a valores
similares a fórmulas para hacer explícita su interpretación como texto.
