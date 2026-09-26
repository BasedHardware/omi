```python
import omi
import json
import sys

def memories_to_jsonl(num_memories=10, output_file="memories.jsonl"):
    """
    Export recent memories into JSON Lines format.

    Args:
        num_memories (int, optional): Number of memories to retrieve. Defaults to 10.
        output_file (str, optional): Name of the output file. Defaults to "memories.jsonl".
    """
    client = omi.Oми()  # Initialize the Omi client
    memories = client.get_memories(num_memories)
    with open(output_file, 'w') as f:
        for mem in memories:
            json_line = json.dumps({
                "text": mem.text,
                "metadata": mem.metadata
            })
            f.write(json_line + "\n")

if __name__ == "__main__":
    memories_to_jsonl()

def test_memories_to_jsonl():
    import os
    test_output = "test_memories.jsonl"
    memories_to_jsonl(num_memories=2, output_file=test_output)
    assert os.path.exists(test_output), "Output file should be created."
    with open(test_output, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 3, "Should have 2 memories plus one empty line."
        for line in lines:
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    assert False, "Each line should be valid JSON."
    os.remove(test_output)
```