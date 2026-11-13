"""G2 Rev 3 transaction primitives. Importing this module activates nothing.

The Firestore walk stays authoritative. Callers own the SQL transaction around
every check and its guarded write. External effects may transmit arbitrarily
late after a successful START; COMPLETE never treats lease expiry as authority.
"""

from .protocol import Fence, FenceRefused, AdmissionChanged, owner_key, conversation_key

__all__ = ['Fence', 'FenceRefused', 'AdmissionChanged', 'owner_key', 'conversation_key']
