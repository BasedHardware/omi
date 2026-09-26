```python
#!/usr/bin/env python
from dataclasses import dataclass
from typing import Optional

import json

@dataclass
class OMISchema:
    id: str
    title: str
    description: str
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class OmiTaskSchema:
    id: str
    title: str
    description: str
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    mode: str = "standard"

def convert_action_items_to_jsonl(
    input_file: str,
    output_file: str,
    mode: str = "standard",
    pending: bool = False,
    deduplicate: bool = False
) -> None:
    schemas = {
        "standard": OMISchema,
        "task_agent": OmiTaskSchema,
        "minimal": lambda: None,
    }

    with open(input_file, "r") as f:
        lines = f.readlines()

    output = []
    seen_ids = set()

    for line in lines:
        if line.strip():
            try:
                data = json.loads(line)
                schema = schemas.get(mode, OMISchema)
                if isinstance(data, dict):
                    if deduplicate and data.get("id") in seen_ids:
                        continue
                    seen_ids.add(data.get("id"))
                    instance = schema(**data)
                    output.append(instance.__dict__)
            except json.JSONDecodeError:
                continue

    with open(output_file, "w") as f:
        for item in output:
            f.write(json.dumps(item) + "\n")

if __name__ == "__main__":
    import sys
    input_file = sys.stdin
    output_file = sys.stdout
    mode = "standard"
    pending = False
    deduplicate = True

    convert_action_items_to_jsonl(
        input_file=input_file,
        output_file=output_file,
        mode=mode,
        pending=pending,
        deduplicate=deduplicate
    )
```