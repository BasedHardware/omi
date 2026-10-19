"""Compatibility alias for ``utils.enrichment.custody`` (plan C2); delete when the last importer moves.

The alias is the same module object, so attribute patches through either name reach the implementation.
The star import only gives type checkers the public names; the module object replaces this one.
"""

import sys

from utils.enrichment import custody as _module
from utils.enrichment.custody import *  # noqa: F401,F403

sys.modules[__name__] = _module
