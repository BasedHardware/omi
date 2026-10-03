```python
import os
from typing import List, Optional
from cli import CLI


class MemoriesToParquet(CLI):
    """
    Convert memories to Apache Parquet format.

    This recipe converts memories into a Parquet file, which is a columnar storage format optimized for analytical workloads.
    The output is stored in the specified path with the .parquet extension.
    """

    @staticmethod
    def arguments() -> List[str]:
        return ["--input", "--output", "--num-rows", "--show-schema"]

    @classmethod
    def cli(cls, args: Optional[list] = None):
        parser = cls._get_parser()
        args = parser.parse_args(args) if args else parser.parse_args()
        cls._main(
            args.input,
            args.output,
            args.num_rows,
            args.show_schema,
        )

    @classmethod
    def _main(
        cls,
        input: str,
        output: str,
        num_rows: Optional[int] = None,
        show_schema: Optional[bool] = None,
    ) -> None:
        """
        Main entry point for the memories to Parquet conversion.

        Args:
            input: Path to the input file.
            output: Path to the output file.
            num_rows: Number of rows to process.
            show_schema: Whether to show the schema.
        """
        # Implementation goes here.
        pass

```

```markdown
# Memories to Parquet

This recipe converts memories into Apache Parquet format.

## Quickstart

### DuckDB
```python
from memories_to_parquet import MemoriesToParquet

MemoriesToParquet().cli([
    "--input", "memories.db",
    "--output", "output.parquet",
])
```

### Polars
```python
from memories_to_parquet import MemoriesToParquet

MemoriesToParquet().cli([
    "--input", "memories.db",
    "--output", "output.parquet",
])
```

### Pandas
```python
from memories_to_parquet import MemoriesToParquet

MemoriesToParquet().cli([
    "--input", "memories.db",
    "--output", "output.parquet",
])
```

## Example

The following command converts memories to Parquet format:

```python
from memories_to_parquet import MemoriesToParquet

MemoriesToParquet().cli([
    "--input", "memories.db",
    "--output", "output.parquet",
])
```

## Parameters

- `--input`: Path to the input file.
- `--output`: Path to the output file.
- `--num-rows`: Number of rows to process.
- `--show-schema`: Show the schema.
```

```markdown
# Examples

## memories_to_parquet

```python
from memories_to_parquet import MemoriesToParquet

MemoriesToParquet().cli([
    "--input", "memories.db",
    "--output", "output.parquet",
])
```

## Examples
```

```python
import os
from typing import List, Optional
from cli import CLI


def test_memories_to_parquet() -> None:
    from memories_to_parquet import MemoriesToParquet

    cmd = [
        "--input",
        "memories.db",
        "--output",
        "output.parquet",
    ]
    result = MemoriesToParquet().cli(cmd)
    assert result is None

    cmd = [
        "--input",
        "memories.db",
        "--output",
        "output.parquet",
        "--num-rows",
        "1000",
    ]
    result = MemoriesToParquet().cli(cmd)
    assert result is None

    cmd = [
        "--input",
        "memories.db",
        "--output",
        "output.parquet",
        "--show-schema",
    ]
    result = MemoriesToParquet().cli(cmd)
    assert result is None

    cmd = [
        "--input",
        "memories.db",
        "--output",
        "output.parquet",
        "--num-rows",
        "1000",
        "--show-schema",
    ]
    result = MemoriesToParquet().cli(cmd)
    assert result is None
```

```