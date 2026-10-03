import csv
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


def clean_text(value):
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return " ".join(value.split())


def clean_tag(value):
    """Normalize tag string for Anki (replace spaces with underscores)."""
    text = clean_text(value)
    return text.replace(" ", "_")


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_memories(sources):
    """Load and deduplicate memories from multiple JSON source files."""
    mem_map = OrderedDict()
    for source in sources:
        path = Path(source)
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, list):
            raise ValueError(f"{source}: expected JSON array from 'omi --json memory list'")
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each memory entry must be a JSON object")
            mem_id = raw.get("id")
            if not isinstance(mem_id, str) or not mem_id:
                raise ValueError(f"{source}: memory item missing non-empty string 'id'")
            mem_map[mem_id] = raw
    return list(mem_map.values())


def format_anki_card(raw, prompt_template="What did I record regarding {category}?"):
    """Format single memory into (Front, Back, Tags) tuple for Anki import."""
    content = clean_text(raw.get("content"))
    category = clean_text(raw.get("category")) or "general"
    created_dt = parse_time(raw.get("created_at"))

    front = prompt_template.format(category=category.capitalize())
    back = content

    tags = ["omi", clean_tag(category)]
    raw_tags = raw.get("tags")
    if isinstance(raw_tags, list):
        for t in raw_tags:
            ct = clean_tag(t)
            if ct and ct not in tags:
                tags.append(ct)
    if created_dt:
        tags.append(f"year_{created_dt.year}")

    return front, back, " ".join(tags)


def convert(sources, destination, category_filter=None, prompt_template="What did I record regarding {category}?"):
    """Convert memory JSON files to Anki-compatible TSV file."""
    memories = load_memories(sources)
    if category_filter:
        cat_lower = category_filter.lower()
        memories = [m for m in memories if clean_text(m.get("category")).lower() == cat_lower]

    output_path = Path(destination)
    try:
        output_file = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None

    buffer = io.StringIO()
    # Anki TSV file format: Front \t Back \t Tags
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    for m in memories:
        front, back, tags_str = format_anki_card(m, prompt_template=prompt_template)
        if back:  # Only export cards with content
            writer.writerow([front, back, tags_str])

    payload = buffer.getvalue().encode("utf-8")
    try:
        with output_file:
            output_file.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(memories)


if __name__ == "__main__":
    args = sys.argv[1:]
    category_filter = None
    prompt_tpl = "What did I record regarding {category}?"

    while args and args[0].startswith("--"):
        if args[0] == "--category":
            if len(args) < 2:
                sys.exit("Error: --category requires an argument")
            category_filter = args[1]
            args = args[2:]
        elif args[0] == "--prompt":
            if len(args) < 2:
                sys.exit("Error: --prompt requires a template argument")
            prompt_tpl = args[1]
            args = args[2:]
        else:
            sys.exit(f"Unknown option: {args[0]}")

    if len(args) < 2:
        sys.exit("Usage: python memories_to_anki.py [--category CAT] [--prompt '... {category} ...'] OUTPUT.tsv INPUT.json [INPUT.json ...]")

    dest = args[0]
    srcs = args[1:]
    try:
        count = convert(srcs, dest, category_filter=category_filter, prompt_template=prompt_tpl)
        print(f"Exported {count} Anki flashcards to {dest}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
