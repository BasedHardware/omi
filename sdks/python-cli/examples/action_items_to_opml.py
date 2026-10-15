import sys
import json
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import os

def parse_args():
    parser = argparse.ArgumentParser(description="Convert Omi Action Items JSON to OPML 2.0")
    parser.add_argument("input", help="Input JSON file (or '-' for stdin)")
    parser.add_argument("output", help="Output OPML file")
    return parser.parse_args()

def safe_get(item, keys, default=""):
    for k in keys:
        if k in item and item[k] is not None:
            return item[k]
    return default

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
        # Extract attributes robustly
        description = safe_get(item, ["description", "text", "title"], "Untitled Action Item")
        
        # Handle completed status
        is_completed = safe_get(item, ["completed", "is_completed"], False)
        if isinstance(is_completed, str):
            is_completed = is_completed.lower() in ('true', 'yes', '1')
        status = "completed" if is_completed else "open"
        
        created = safe_get(item, ["created_at", "created"], "")
        due = safe_get(item, ["due_at", "due_date", "due"], "")
        
        # Create outline element
        attribs = {
            "text": str(description),
            "_status": status,
        }
        if created:
            attribs["created"] = str(created)
        if due:
            attribs["due"] = str(due)
            
        ET.SubElement(body, "outline", attribs)
        
    return opml

def get_opml_string(elem):
    if hasattr(ET, 'indent'):
        ET.indent(elem, space="  ", level=0)
    xml_bytes = ET.tostring(elem, encoding="UTF-8", xml_declaration=True)
    return xml_bytes.decode('utf-8')

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

def main():
    args = parse_args()
    
    # Read input
    if args.input == '-':
        data = json.load(sys.stdin)
    else:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
    # Ensure it's a list
    if not isinstance(data, list):
        if "items" in data:
            data = data["items"]
        else:
            data = [data] if data else []
            
    # Create OPML tree
    opml_tree = create_opml(data)
    
    # Format to string
    opml_str = get_opml_string(opml_tree)
    
    # Write output
    atomic_write(args.output, opml_str)
    
if __name__ == "__main__":
    main()