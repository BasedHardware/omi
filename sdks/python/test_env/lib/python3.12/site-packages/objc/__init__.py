"""
Python <-> Objective-C bridge (PyObjC)

This module defines the core interfaces of the Python<->Objective-C bridge.
"""

from . import _objc


# Import the namespace from the _objc extension
def _update(g):
    for k in _objc.__dict__:
        g.setdefault(k, getattr(_objc, k))


_update(globals())
del _update


from ._transform import *  # noqa: F401, F403, E402
from ._convenience import *  # noqa: F401, F403, E402
from ._convenience_nsobject import *  # noqa: F401, F403, E402
from ._convenience_nsdecimal import *  # noqa: F401, F403, E402
from ._convenience_nsdata import *  # noqa: F401, F403, E402
from ._convenience_nsdictionary import *  # noqa: F401, F403, E402
from ._convenience_nsset import *  # noqa: F401, F403, E402
from ._convenience_nsarray import *  # noqa: F401, F403, E402
from ._convenience_nsstring import *  # noqa: F401, F403, E402
from ._convenience_mapping import *  # noqa: F401, F403, E402
from ._convenience_sequence import *  # noqa: F401, F403, E402
from ._dyld import *  # noqa: F401, F403, E402
from ._protocols import *  # noqa: F401, F403, E402
from ._descriptors import *  # noqa: F401, F403, E402
from ._category import *  # noqa: F401, F403, E402
from ._bridges import *  # noqa: F401, F403, E402
from ._pythonify import *  # noqa: F401, F403, E402
from ._locking import *  # noqa: F401, F403, E402
from ._context import *  # noqa: F401, F403, E402
from ._properties import *  # noqa: F401, F403, E402
from ._lazyimport import *  # noqa: F401, F403, E402
from ._compat import *  # noqa: F401, F403, E402
from ._bridgesupport import *  # noqa: F401, F403, E402
from . import _structtype  # noqa: F401, F403, E402
from . import _callable_docstr  # noqa: F401, F403, E402
from . import _pycoder  # noqa: F401, F403, E402
from ._informal_protocol import *  # noqa: F401, F403, E402
from . import _new  # noqa: F401, E402


# Helper function for new-style metadata modules
def _resolve_name(name):
    if "." not in name:
        raise ValueError(name)

    module, name = name.rsplit(".", 1)
    m = __import__(module)
    for k in module.split(".")[1:]:
        m = getattr(m, k)

    return getattr(m, name)


_NSAutoreleasePool = None

# Aliases for some common Objective-C constants
nil = None
YES = True
NO = False


class autorelease_pool:
    """
    A context manager that runs the body of the block with a fresh
    autorelease pool. The actual release pool is not accessible.
    """

    def __init__(self):
        global _NSAutoreleasePool
        if _NSAutoreleasePool is None:
            _NSAutoreleasePool = lookUpClass("NSAutoreleasePool")  # noqa: F405

    def __enter__(self):
        self._pool = _NSAutoreleasePool.alloc().init()

    def __exit__(self, exc_type, value, tp):
        del self._pool
