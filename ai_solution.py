```python
# sdks/python-cli/examples/conversations_to_jsonl.py
import json
import time
from typing import List, Optional
from ..conversations import Conversation


def conversations_to_jsonl(
    path: str = "conversations.jsonl",
    mode: str = "standard",
    include_vectors: bool = False,
) -> str:
    """Exports conversation history to JSON Lines format.

    Args:
        path: Path to the output file.
        mode: Mode to use for the JSONL export.
        include_vectors: Whether to include vector embeddings.

    Returns:
        The path to the output file.
    """
    try:
        # Get the conversation history
        convs: List[dict] = []
        for conv in Conversation.get_conversations():
            conv_dict = conv.dict()
            if include_vectors:
                conv_dict["vector"] = conv.get_vector()
            convs.append(conv_dict)
        
        # Calculate duration
        start_time = time.time()
        # Process the data
        with open(path, "w") as f:
            for item in convs:
                json_line = json.dumps(item)
                f.write(json_line + "\n")
        duration = time.time() - start_time

        return path
    except Exception as e:
        raise e


# tests/test_conversations_to_jsonl.py
import json
import time
from unittest.mock import patch
from ..conversations_to_jsonl import conversations_to_jsonl


def test_conversations_to_jsonl(tmp_path):
    """Test the conversations_to_jsonl function."""
    test_path = tmp_path / "test_conversations.jsonl"
    
    with patch("time.time") as mock_time:
        mock_time.return_value = 1000
        result = conversations_to_jsonl(path=test_path, mode="standard")
        assert result == test_path
        assert test_path.exists()
        
    # Verify the output
    with open(test_path) as f:
        lines = f.readlines()
        assert len(lines) > 0
        for line in lines:
            try:
                json.loads(line.strip())
            except json.JSONDecodeError:
                assert False, "JSON decoding error in output."

    # Test with vectors
    with patch("time.time") as mock_time:
        mock_time.return_value = 1000
        result = conversations_to_jsonl(path=test_path, include_vectors=True)
        assert result == test_path
        assert test_path.exists()

    # Verify the output with vectors
    with open(test_path) as f:
        lines = f.readlines()
        assert len(lines) > 0
        for line in lines:
            try:
                json.loads(line.strip())
            except json.JSONDecodeError:
                assert False, "JSON decoding error in output with vectors."
```

```markdown
# sdks/python-cli/examples/conversations_jsonl.md
```