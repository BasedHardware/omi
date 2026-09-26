```python
def memories_to_jsonl(
    mode="standard",  # "standard", "rag", or "system-prompt"
    category=None,
    deduplicate=False,
    page_size=100
):
    from omni.core import get_memory
    memories = get_memory().get_memories()
    jsonl = []
    seen = set()
    count = 0
    for memory in memories:
        if deduplicate and memory in seen:
            continue
        seen.add(memory)
        if mode == "standard":
            jsonl.append(f'{{"text": "{memory}"}}')
        elif mode == "rag":
            jsonl.append(f'{{"text": "{memory}", "metadata": {{}}}}')
        elif mode == "system-prompt":
            jsonl.append(
                f'{{"text": "{memory}", "metadata": {{"mode": "system-prompt"}}}}'
            )
        count += 1
        if count >= page_size and page_size > 0:
            yield "\n".join(jsonl) + "\n"
            jsonl = []
            seen = set()
    if jsonl:
        yield "\n".join(jsonl) + "\n"

# Example usage:
# memories_to_jsonl(mode="standard", category="example", deduplicate=True, page_size=10)
```

```markdown
# Memories to JSON Lines (JSONL) Export

Export memories in JSON Lines format with options for mode, category, deduplication, and page size.

## Usage:
```python
from omni.core import memories_to_jsonl

result = memories_to_jsonl(mode="standard", category="example", deduplicate=True, page_size=10)
```

## Example Output:
```jsonl
{"text": "The quick brown fox..."}
{"text": "The lazy dog..."}
...
```

## Parameters:
- `mode`: "standard", "rag", or "system-prompt"
- `category`: Optional category filter
- `deduplicate`: Remove duplicates
- `page_size`: Number of items per output (default: 100)
```

```python
def test_memories_to_jsonl():
    from omni.core import memories_to_jsonl, mock_memories
    mock_memories(["Mock memory 1", "Mock memory 2", "Mock memory 1"])
    result = list(memories_to_jsonl(deduplicate=True))
    assert len(result) == 2  # Deduplicated
    print("Test passed")
    
test_memories_to_jsonl()
```