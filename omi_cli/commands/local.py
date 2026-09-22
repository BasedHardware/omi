import re
from typing import Dict, List, Optional

# Existing imports and code omitted for brevity

def _parse_sql_table(text: str) -> Optional[Dict]:
    """
    Attempt to parse a Desktop SQL table string into a structured JSON object.
    Returns None if the text does not look like a table.
    """
    lines = [line.rstrip() for line in text.strip().splitlines()]
    if len(lines) < 3:
        return None

    header_line = lines[0]
    separator_line = lines[1]

    # Basic check that the separator line contains only dashes, pipes and spaces
    if not re.fullmatch(r"[ \-|]+", separator_line):
        return None

    columns = [col.strip() for col in header_line.split("|")]
    if not columns or any(not col for col in columns):
        return None

    rows: List[Dict[str, str]] = []
    for line in lines[2:]:
        line = line.strip()
        if not line:
            continue
        # Skip the row count line (e.g., "1 row(s)")
        if re.search(r"\d+\s+row\(s\)", line, re.IGNORECASE):
            continue
        if "|" not in line:
            continue
        values = [val.strip() for val in line.split("|")]
        if len(values) != len(columns):
            continue
        rows.append(dict(zip(columns, values)))

    return {"columns": columns, "rows": rows, "row_count": len(rows)}


def _normalize_sql_result(table: str) -> Dict:
    """
    Normalise the raw SQL output from the Desktop into a JSON-friendly format.
    The function first attempts to parse the output as a table.  If that fails,
    it falls back to the legacy status/error handling logic.
    """
    # 1. Try to parse as a table first
    parsed = _parse_sql_table(table)
    if parsed is not None:
        return parsed

    # 2. Legacy status/error handling
    if table.startswith("SQL Error:"):
        return {"error": table}
    if table.startswith("OK:"):
        return {"ok": True, "message": table}
    return {"message": table}
