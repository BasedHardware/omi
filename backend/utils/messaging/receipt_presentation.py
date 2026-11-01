"""App receipt cards own the outcome text; channel bubbles retain their prose."""

from typing import Any, Mapping, Sequence


def app_receipt_text(text: str, blocks: Sequence[Mapping[str, Any]], *, surface: str = 'app') -> str:
    """Avoid repeating model-written outcomes beside the native edit receipt.

    Mobile recognizes this canonical summary body and renders the cards once.
    Older clients can still display the outcome as ordinary text. Existing create blocks
    and read-only replies retain their current body behavior.
    """
    if surface == 'app' and any(block.get('type') == 'editReceipt' for block in blocks):
        outcomes = []
        for block in blocks:
            if block.get('type') == 'editReceipt':
                outcomes.append(str(block.get('summary') or 'Change').strip())
            elif block.get('type') == 'taskCard':
                outcomes.append('Task')
            elif block.get('type') == 'memoryLink':
                summary = str(block.get('summary') or '').strip()
                outcomes.append('Memory - ' + summary if summary else 'Memory')
        return '\n'.join(outcomes)
    return text
