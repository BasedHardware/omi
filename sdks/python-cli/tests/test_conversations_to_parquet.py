```python
"""
Tests for the conversations to Apache Parquet conversion recipe.
"""

import json
import tempfile
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def sample_conversations() -> list[dict]:
    """Sample conversations data for testing."""
    return [
        {
            "id": "conversation_1",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2023-01-01T00:00:00Z",
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "timestamp": "2023-01-01T00:00:01Z",
                },
            ],
        },
        {
            "id": "conversation_2",
            "messages": [
                {
                    "role": "user",
                    "content": "How are you?",
                    "timestamp": "2023-01-01T00:00:02Z",
                },
            ],
        },
    ]


def test_conversion(sample_conversations: list[dict]) -> None:
    """Test the conversion of conversations to Parquet."""
    from sdks.python_cli.examples.conversations_to_parquet import (
        convert_conversations_to_parquet,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "conversations.json"
        output_path = Path(temp_dir) / "conversations.parquet"

        # Write sample data
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sample_conversations, f)

        # Convert
        convert_conversations_to_parquet(input_path, output_path)

        # Verify output
        assert output_path.exists()

        # Read and verify the data
        df = pl.read_parquet(output_path)
        assert df.shape == (3, 4)  # 3 messages, 4 columns

        # Check columns
        expected_columns = ["conversation_id", "role", "content", "timestamp"]
        assert df.columns == expected_columns

        # Check data
        records = df.to_dicts()
        assert records[0] == {
            "conversation_id": "conversation_1",
            "role": "user",
            "content": "Hello",
            "timestamp": "2023-01-01T00:00:00Z",
        }
        assert records[1] == {
            "conversation_id": "conversation_1",
            "role": "assistant",
            "content": "Hi there!",
            "timestamp": "2023-01-01T00:00:01Z",
        }
        assert records[2] == {
            "conversation_id": "conversation_2",
            "role": "user",
            "content": "How are you?",
            "timestamp": "2023-01-01T00:00:02Z",
        }


def test_main_function(sample_conversations: list[dict]) -> None:
    """Test the main function with command line arguments."""
    import sys
    from sdks.python_cli.examples.conversations_to_parquet import main

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "conversations.json"
        output_path = Path(temp_dir) / "conversations.parquet"

        # Write sample data
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sample_conversations, f)

        # Mock command line arguments
        sys.argv = ["conversations_to_parquet.py", str(input_path), str(output_path)]

        # Run main
        main()

        # Verify output
        assert output_path.exists()

        # Read and verify the data
        df = pl.read_parquet(output_path)
        assert df.shape == (3, 4)


def test_empty_conversations() -> None:
    """Test conversion with empty conversations."""
    from sdks.python_cli.examples.conversations_to_parquet import (
        convert_conversations_to_parquet,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "conversations.json"
        output_path = Path(temp_dir) / "conversations.parquet"

        # Write empty data
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        # Convert
        convert_conversations_to_parquet(input_path, output_path)

        # Verify output
        assert output_path.exists()

        # Read and verify the data
        df = pl.read_parquet(output_path)
        assert df.shape == (0, 4)  # 0 messages, 4 columns
        assert df.columns == ["conversation_id", "role", "content", "timestamp"]