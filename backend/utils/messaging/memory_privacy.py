"""Keep private memories out of chat-app retrieval. The app surface is unchanged.

A channel turn withholds a memory when the link's keep-private-in-app setting is on
(the default). That covers memories the user marked private and rows carrying a
restricted sensitivity label (health, money, credentials, and the rest of that set).
"""

from models.product_memory import RESTRICTED_SENSITIVITY_LABELS
from utils.messaging.projection import surface_runtime

_RESTRICTED = {label.lower() for label in RESTRICTED_SENSITIVITY_LABELS}


def channel_private_filter_active(configurable=None) -> bool:
    if isinstance(configurable, dict) and configurable.get('withhold_private_memories'):
        return True
    runtime = surface_runtime.get()
    return bool(runtime is not None and runtime.withhold_private_memories)


def is_channel_private_memory(memory) -> bool:
    if isinstance(memory, dict):
        visibility = memory.get('visibility')
        labels = memory.get('sensitivity_labels') or ()
    else:
        visibility = getattr(memory, 'visibility', None)
        labels = getattr(memory, 'sensitivity_labels', None) or ()
    if str(visibility or '').strip().lower() == 'private':
        return True
    normalized = set()
    for label in labels:
        text = getattr(label, 'value', label)
        if isinstance(text, str) and text.strip():
            normalized.add(text.strip().lower())
    return bool(normalized & _RESTRICTED)


def omit_channel_private(rows, configurable=None):
    if not channel_private_filter_active(configurable):
        return rows
    return [row for row in rows if not is_channel_private_memory(row)]
