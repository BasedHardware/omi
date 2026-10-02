To solve the problem, we introduce a helper function to ensure sections are dictionaries. Here's the code:

```python
def _receipt_section(receipt, key):
    """Return the section if it's a Mapping, else return empty."""
    section = receipt.get(key)
    return section if isinstance(section, dict) else {}

# Example usage in manual_speaker_assignments.py:
manual_speaker_assignments = _receipt_section(manual_speaker_assignments, 'manual_speaker_assignments')
manual_rejected_speakers = _receipt_section(manual_speaker_assignments, 'manual_rejected_speakers')
manual_owner_reserved = _receipt_section(manual_speaker_assignments, 'manual_owner_reserved')
apply_manual_assignments = _receipt_section(manual_speaker_assignments, 'apply_manual_assignments')
```

This ensures each section is a dictionary, preventing `AttributeError` when they're lists.