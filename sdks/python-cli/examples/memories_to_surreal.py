import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def strip_surrogates(value):
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value):
    """Return a printable string for any JSON scalar/container."""
    if value is None:
        return ""
    if isinstance(value, str):
        return strip_surrogates(value)
    return strip_surrogates(json.dumps(value, ensure_ascii=False, sort_keys=True))


def utc_stamp(value):
    """Normalise an ISO-8601 timestamp to `YYYY-MM-DD HH:MM:SS` UTC text."""
    if not value:
        return ""
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ics_stamp(value):
    """Normalise a timestamp to iCalendar UTC form `YYYYMMDDTHHMMSSZ`."""
    if not value:
        return ""
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_export(path):
    """Read a saved `omi --json` export; must be a JSON array."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"cannot read {path!r}: {exc}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path!r} is not valid JSON: {exc}")
    if not isinstance(data, list):
        raise SystemExit(f"{path!r}: expected a JSON array, got {type(data).__name__}")
    return data


def check_out_path(path):
    """Refuse path traversal; warn-free overwrite only for our own outputs."""
    p = Path(path)
    if ".." in p.parts:
        raise SystemExit(f"output path {path!r} contains '..'; refusing to write")
    return p


def dig(obj, dotted):
    """Resolve a dotted path ('a.b.c') through nested dicts; None if missing."""
    cur = obj
    for part in dotted.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur

def main(argv):
    if len(argv) != 3:
        print(f"usage: {argv[0]} <export.json> <out.surql>", file=sys.stderr)
        return 2
    data = load_export(argv[1])
    out = check_out_path(argv[2])
    lit = lambda s: "'" + s.replace("'", "\\'") + "'"
    lines = [f"-- SurrealQL import for omi memories"]
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        rid = text(item.get("id")) or str(i)
        fields = ", ".join(f"{k.replace('.', '_')}: {lit(utc_stamp(text(dig(item, k))) if k.endswith('_at') else text(dig(item, k)))}" for k in ['id', 'content', 'category', 'created_at', 'updated_at', 'conversation_id'])
        lines.append(f"CREATE memories:`{rid}` SET {fields}, raw_json = {lit(json.dumps(item, ensure_ascii=False))};")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} — load with: surreal import --conn http://localhost:8000 --ns omi --db omi {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
