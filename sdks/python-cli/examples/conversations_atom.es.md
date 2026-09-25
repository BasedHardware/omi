# Publicar tus conversaciones como un feed Atom

Utiliza esta receta para seguir tus propias grabaciones de Omi en un lector de feeds: convierte una
o más exportaciones de `conversation list` en un único archivo Atom 1.0 al cual aplicaciones como NetNewsWire,
Thunderbird, la importación local de Feedly o cualquier otro lector pueden suscribirse mediante una
ruta `file://`. Cada conversación se convierte en una entrada con su título, categoría,
marcas de tiempo y un resumen de metadatos de una línea, ordenadas de más reciente a más antigua. Lee exportaciones
JSON guardadas, no realiza peticiones de red, no exporta transcripciones y genera un único
archivo XML. Necesitas Python 3.10+ y un `omi-cli` autenticado para la
exportación inicial.

Exporta las conversaciones que deseas incluir en el feed (200 por página):

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verifica que el comando se ejecutó correctamente antes de convertir el archivo. Si una página está completa,
obtén la siguiente con `--offset 200` en un segundo archivo; el conversor
acepta múltiples archivos e incluye cada ID de conversación una sola vez.

Guarda lo siguiente como `conversations_to_atom.py`:

```python
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

FEED_TITLE = "Conversaciones de Omi"
FEED_ID = "urn:omi:conversations"
EPOCH = "1970-01-01T00:00:00Z"


def text(value):
    """Representa un campo como una línea de texto segura para XML.

    La API de desarrollo es de tipado flexible, por lo que un campo puede llegar como un tipo distinto
    de cadena aunque el CLI lo modele como string; cualquier valor no nulo se convierte en lugar
    de ser rechazado. XML 1.0 no posee secuencia de escape para caracteres de control C0 ni
    codificación para subrogados aislados, por lo que se omiten aquí para evitar corromper el feed.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    return "".join(ch for ch in collapsed if ch >= " " and not "\ud800" <= ch <= "\udfff")


def parse_time(value):
    """Convierte una marca de tiempo ISO-8601 en un datetime UTC consciente, o None si no es utilizable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rfc3339(moment):
    """Las marcas de tiempo de Atom siguen el estándar RFC 3339; el feed las conserva en UTC."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def load(sources):
    conversations = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: se esperaba el arreglo JSON de omi --json conversation list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: cada conversación debe ser un objeto")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: cada conversación requiere un id de tipo cadena")
            structured = item.get("structured")
            if structured is None:
                structured = {}
            if not isinstance(structured, dict):
                raise ValueError(f"{source}: el campo structured de la conversación debe ser un objeto o null")
            conversations[item_id] = item
    return conversations


def entries(conversations):
    """Construye una entrada por conversación, ordenadas de más reciente a más antigua."""
    rows = []
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        structured = item.get("structured") or {}
        complete = start is not None and end is not None and end >= start
        seconds = int((end - start).total_seconds()) if complete else 0
        details = [f"Duración: {seconds / 60:.0f} min"]
        for label, value in (("Categoría", text(structured.get("category"))),
                             ("Carpeta", text(item.get("folder_name"))),
                             ("Origen", text(item.get("source"))),
                             ("Idioma", text(item.get("language")))):
            if value:
                details.append(f"{label}: {value}")
        rows.append({
            "id": item_id,
            "title": text(structured.get("title")) or "(conversación sin título)",
            "category": text(structured.get("category")),
            "published": start,
            # Una entrada requiere hora de actualización: el final de la grabación o su
            # inicio cuando falta el fin o es anterior al inicio.
            "updated": end if complete else start,
            "summary": " - ".join(details),
            "sort": start if start is not None else datetime.min.replace(tzinfo=timezone.utc),
        })
    rows.sort(key=lambda row: (row["sort"], row["id"]), reverse=True)
    return rows


def feed(rows):
    stamps = [rfc3339(row["updated"]) for row in rows if row["updated"] is not None]
    parts = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>",
             "<feed xmlns=\"http://www.w3.org/2005/Atom\">",
             f"<title>{escape(FEED_TITLE)}</title>",
             f"<id>{FEED_ID}</id>",
             # Todas las marcas están en UTC y ancho fijo, por lo que la más reciente queda al final.
             f"<updated>{max(stamps) if stamps else EPOCH}</updated>",
             "<author><name>Omi</name></author>"]
    for row in rows:
        # La codificación por porcentaje mantiene el id de entrada como un IRI válido;
        # un ID de conversación estándar se transmite sin cambios.
        parts += ["<entry>",
                  f"<title>{escape(row['title'])}</title>",
                  f"<id>urn:omi:conversation:{quote(row['id'], safe='')}</id>",
                  f"<updated>{rfc3339(row['updated']) if row['updated'] is not None else EPOCH}</updated>"]
        if row["published"] is not None:
            parts.append(f"<published>{rfc3339(row['published'])}</published>")
        if row["category"]:
            parts.append(f"<category term={quoteattr(row['category'])}/>")
        parts += [f"<summary type=\"text\">{escape(row['summary'])}</summary>", "</entry>"]
    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def convert(sources, destination):
    rows = entries(load(sources))
    # Construye y codifica todo el feed antes de escribir en disco.
    payload = feed(rows).encode("utf-8")
    output_path = Path(destination)
    # La creación exclusiva protege un feed existente; una escritura fallida no deja un archivo parcial.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Se rechaza sobrescribir el archivo existente {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(rows)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("Uso: python conversations_to_atom.py SALIDA.xml ENTRADA.json [ENTRADA.json ...]")
    try:
        count = convert(args[1:], args[0])
    except (OSError, ValueError) as exc:
        sys.exit(f"Falló la exportación Atom: {exc}")
    print(f"{count} entrada{'s' if count != 1 else ''} guardada{'s' if count != 1 else ''} en {args[0]}")
```

Ejecútalo (el archivo de salida va primero, seguido de una o más exportaciones):

```sh
python conversations_to_atom.py conversations.xml conversations.json
```

Agrega el archivo resultante a tu lector como una suscripción local, o comparte la carpeta
mediante HTTP si tu lector no admite rutas `file://`. Las entradas se ordenan de más
reciente a más antigua; cada una incluye el título de la conversación, la `category` como
un término de categoría Atom, `published` (`started_at`), `updated` (`finished_at`, o el
inicio cuando falta el final o es anterior al inicio) y un resumen en texto plano
con la duración, carpeta, origen e idioma. Los títulos y las categorías provienen
del objeto `structured` que retorna la API, por lo que no se lee ni escribe
texto de transcripciones. Cada valor se escapa en formato XML, los caracteres de control y
subrogados aislados se eliminan, y los IDs de entrada se codifican con porcentaje, garantizando
que un título o ID inusual produzca un feed válido y procesable. Ejecutar nuevamente con más
archivos de exportación regenera el feed listando cada conversación una sola vez; el script
rechaza sobrescribir un archivo existente, por lo que debes eliminar el archivo antiguo o indicar
un nombre nuevo. Trata el feed como información privada — es un registro detallado de cuándo y sobre
qué estuviste grabando.
