#!/usr/bin/env python3
"""
Omi memory JSON to Joplin Markdown/JEX converter.
"""
import argparse
import json
import os
import re
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, TextIO

__version__ = "0.1.0"

# Constants
DEFAULT_NOTEBOOK = "Omi Memories"
DEFAULT_TAGS = ["omi", "memory"]
JEX_MIME_TYPE = "application/x-joplin-export"

class MemoryConverter:
    """Core conversion logic for Omi memories to Joplin format."""

    def __init__(self):
        self._seen_ids: Set[str] = set()

    def sanitize_filename(self, title: str) -> str:
        """Sanitize string for filesystem paths."""
        return re.sub(r'[^a-zA-Z0-9\s\-]', '_', title).strip().replace(' ', '_')

    def memory_to_markdown(self, memory: Dict) -> str:
        """Convert Omi memory to Joplin Markdown with YAML frontmatter."""
        memory_id = memory.get('id')
        if memory_id in self._seen_ids:
            return ""
        self._seen_ids.add(memory_id)

        title = memory.get('title', 'Untitled Memory')
        content = memory.get('content', '')
        created_at = memory.get('createdAt', '')
        updated_at = memory.get('updatedAt', '')
        tags = memory.get('tags', [])

        # Convert timestamps to ISO format
        created_dt = datetime.fromtimestamp(created_at / 1000) if created_at else datetime.now()
        updated_dt = datetime.fromtimestamp(updated_at / 1000) if updated_at else created_dt

        frontmatter = f"""---
title: {title}
notebook: {DEFAULT_NOTEBOOK}
tags:
{'\n'.join(f'- {tag}' for tag in DEFAULT_TAGS + tags)}
created_time: {created_dt.isoformat()}
updated_time: {updated_dt.isoformat()}
---"""

        return f"{frontmatter}\n\n{content}"

    def create_jex_archive(self, output_path: str, memories: List[Dict]) -> None:
        """Create Joplin JEX archive from memories."""
        with tarfile.open(output_path, 'w:gz') as tar:
            tarinfo = tar.gettarinfo(output_path)
            tarinfo.mtime = int(datetime.now().timestamp())
            tarinfo.size = 0
            tarinfo.mime_type = JEX_MIME_TYPE
            tar.addfile(tarinfo, io.BytesIO(b""))

            for memory in memories:
                memory_id = memory.get('id')
                if memory_id in self._seen_ids:
                    continue
                self._seen_ids.add(memory_id)

                title = self.sanitize_filename(memory.get('title', 'untitled'))
                content = self.memory_to_markdown(memory)
                tarinfo = tar.gettarinfo(f"{title}.md")
                tarinfo.mtime = int(datetime.now().timestamp())
                tar.addfile(tarinfo, io.BytesIO(content.encode('utf-8')))

    def process_input(self, input_path: Optional[str], output_path: str, force: bool) -> None:
        """Process input file(s) and write output."""
        memories: List[Dict] = []

        if input_path == '-':
            # Read from stdin
            input_data = sys.stdin.read()
            try:
                memories = json.loads(input_data)
                if not isinstance(memories, list):
                    memories = [memories]
            except json.JSONDecodeError as e:
                sys.stderr.write(f"Error parsing JSON: {e}\n")
                sys.exit(1)
        else:
            # Read from file(s)
            if os.path.isdir(input_path):
                for file_path in Path(input_path).glob('*.json'):
                    with open(file_path, 'r') as f:
                        try:
                            memories.extend(json.load(f))
                        except json.JSONDecodeError:
                            sys.stderr.write(f"Skipping invalid JSON: {file_path}\n")
            else:
                with open(input_path, 'r') as f:
                    try:
                        memories = json.load(f)
                        if not isinstance(memories, list):
                            memories = [memories]
                    except json.JSONDecodeError as e:
                        sys.stderr.write(f"Error parsing JSON: {e}\n")
                        sys.exit(1)

        # Determine output type
        if output_path.endswith('.jex'):
            self.create_jex_archive(output_path, memories)
        else:
            os.makedirs(output_path, exist_ok=True)
            for memory in memories:
                markdown = self.memory_to_markdown(memory)
                if not markdown:
                    continue
                filename = self.sanitize_filename(memory.get('title', 'untitled')) + '.md'
                output_file = os.path.join(output_path, filename)
                if os.path.exists(output_file) and not force:
                    sys.stderr.write(f"Skipping existing file: {output_file}\n")
                    continue
                with open(output_file, 'w') as f:
                    f.write(markdown)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Convert Omi memory JSON to Joplin Markdown/JEX format',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input', nargs='?', default='-', 
                       help='Input JSON file or directory (default: stdin)')
    parser.add_argument('output', help='Output directory or .jex archive path')
    parser.add_argument('--force', action='store_true', 
                       help='Overwrite existing files')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args()

    converter = MemoryConverter()
    converter.process_input(args.input, args.output, args.force)


if __name__ == '__main__':
    main()