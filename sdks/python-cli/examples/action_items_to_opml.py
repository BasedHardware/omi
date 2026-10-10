import sys
import json
import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import os

DONE_WORDS = {"true", "yes", "1", "done", "completed"}

def parse_args():
    parser = argparse.ArgumentParser(description="Convert Omi Action Items JSON to OPML 2.0")
    parser.add_argument("input", help="Input JSON file (or '-' for stdin)")
    parser.add_argument("output", help="Output OPML file")
    return parser.parse_args()

def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")

def sanitize_xml_text(value) -> str:
    """Normalize text and strip invalid XML 1.0 control characters and surrogates."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = strip_surrogates(text)
    # Remove XML 1.0 disallowed control characters (keep tab, lf, cr)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

def is_completed(value) -> bool:
    """Normalize completed status handling booleans, numbers, and loose strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False

def safe_get(item, keys, default=""):
    for k in keys:
        if k in item and item[k] is not None:
            return item[k]
    return default

def extract_action_items(data):
    """Unwrap action items from bare lists or documented envelope dicts."""
    if isinstance(data, list):
        return [it for it in data if isinstance(it, dict)]
    if isinstance(data, dict):
        for key in ("action_items", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [it for it in val if isinstance(it, dict)]
        if data:
            return [data]
    return []

def create_opml(action_items):
    # Create the root element
    opml = ET.Element("opml", version="2.0")
    
    # Create head
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "Omi Action Items"
    ET.SubElement(head, "dateCreated").text = datetime.now(timezone.utc).isoformat()
    
    # Create body
    body = ET.SubElement(opml, "body")
    
    for item in action_items:
        if not isinstance(item, dict):
            continue
        # Extract attributes robustly
        raw_desc = safe_get(item, ["description", "text", "title"], "Untitled Action Item")
        description = sanitize_xml_text(raw_desc) or "Untitled Action Item"
        
        # Handle completed status
        comp_val = safe_get(item, ["completed", "is_completed"], False)
        status = "completed" if is_completed(comp_val) else "open"
        
        created = sanitize_xml_text(safe_get(item, ["created_at", "created"], ""))
        due = sanitize_xml_text(safe_get(item, ["due_at", "due_date", "due"], ""))
        
        # Create outline element
        attribs = {
            "text": description,
            "_status": status,
        }
        if created:
            attribs["created"] = created
        if due:
            attribs["due"] = due
            
        ET.SubElement(body, "outline", attribs)
        
    return opml

def get_opml_string(elem):
    if hasattr(ET, 'indent'):
        ET.indent(elem, space="  ", level=0)
    xml_bytes = ET.tostring(elem, encoding="UTF-8", xml_declaration=True)
    return strip_surrogates(xml_bytes.decode('utf-8'))

def atomic_write(filepath, content):
    path = Path(filepath)
    partial_path = path.with_suffix(path.suffix + '.partial')
    try:
        with open(partial_path, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(partial_path, path)
    except Exception as e:
        if partial_path.exists():
            os.remove(partial_path)
        raise e

def load_input_data(input_src: str):
    """Load and normalize action items from stdin or file safely."""
    if input_src == "-":
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    else:
        path = Path(input_src)
        if not path.is_file():
            sys.stderr.write(f"Error: file not found: {path}\n")
            sys.exit(1)
        raw = path.read_bytes().decode("utf-8-sig", errors="replace")
        
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        sys.exit(1)
    return extract_action_items(data)

def main():
    args = parse_args()
    data = load_input_data(args.input)
    opml_tree = create_opml(data)
    opml_str = get_opml_string(opml_tree)
    atomic_write(args.output, opml_str)
    
if __name__ == "__main__":
    main()