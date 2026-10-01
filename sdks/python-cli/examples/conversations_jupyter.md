# Export Omi Conversations to Jupyter Notebooks (.ipynb)

Convert conversation history into Jupyter notebooks for interactive analysis, pandas querying, and visualization.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` session (`omi auth login` or API key configured)
- `pandas` (optional, for notebook data analysis)

## Quickstart

```bash
# Export all conversations to a single combined notebook
python examples/conversations_to_jupyter.py conversations.json -o analysis.ipynb

# Pipe directly from omi CLI
omi --json conversation list --include-transcript | python examples/conversations_to_jupyter.py - -o omi_analysis.ipynb

# Export one notebook per conversation into a folder
python examples/conversations_to_jupyter.py conversations.json --output-dir ./notebooks/
```

## Structure of Generated Notebooks

Each conversation becomes an interactive section:
1. **Markdown Cell:** Title, timestamp, metadata, overview summary, and action items checklist.
2. **Code Cell:** A structured Python list `transcript = [{"speaker": "...", "start": 0.0, "end": 1.5, "text": "..."}]` ready to convert to a pandas DataFrame:

```python
import pandas as pd
df = pd.DataFrame(transcript)
df.head()
```
