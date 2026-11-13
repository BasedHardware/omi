# Omi conversations → Jupyter notebook recipe

Turn a conversation export from the Omi CLI into a Jupyter notebook (`.ipynb`) you
can open in Jupyter, JupyterLab, or VS Code: one section per conversation with its
summary and action items, plus a `transcript` variable you can slice with pandas.

```sh
# one master notebook
omi --json conversation list --include-transcript > conversations.json
python examples/conversations_to_jupyter.py conversations.json omi_conversations.ipynb

# straight from the pipe
omi --json conversation list | python examples/conversations_to_jupyter.py - omi_conversations.ipynb

# one notebook per conversation into a folder
python examples/conversations_to_jupyter.py conversations.json "" --output-dir notebooks/
```

The script is self-contained: standard library only, no dependencies to install.

## What you get

Each conversation becomes a section:

```markdown
## 1. Planning the launch

- **ID:** conv_123
- **Started:** 2026-09-01 09:00:00 UTC
- **Source:** `omi`
- **Category:** `meeting`
- **Transcript:** 14 segment(s), 2 speaker(s)

### Summary
We agreed on a September 15 beta, with rollout starting at 5%.

### Action items
- [x] Draft the rollout plan
- [ ] Set up the feature flag
```

and a code cell holding the transcript, ready for tabular analysis:

```python
# Omi conversation 1 (conv_123)
transcript = [
  {
    "speaker": "Speaker 1",
    "start": "00:00",
    "end": "00:03",
    "text": "Hi, ready to walk through the launch plan?"
  }
]
len(transcript)
```

Then explore it with pandas in the next cell:

```python
import pandas as pd

df = pd.DataFrame(transcript)
df.groupby("speaker")["text"].apply(" ".join)   # one blob per speaker
```

## Notes

- **Deterministic.** No timestamps are generated at write time, so the same export
  always produces the same notebook bytes.
- **No-overwrite guard.** The master notebook is created with an exclusive write and
  refuses to replace an existing file; pass `--overwrite` to replace it. Per-conversion
  files in `--output-dir` are never clobbered — collisions get `-2`, `-3`, …
- **Loose types tolerated.** Missing fields, stringly-typed numbers, and absent
  transcript segments all degrade to empty values instead of crashing the export.
- **Valid nbformat 4.** The output is plain JSON conforming to the notebook format,
  so it opens anywhere a `.ipynb` does; re-saving in Jupyter upgrades it in place.
