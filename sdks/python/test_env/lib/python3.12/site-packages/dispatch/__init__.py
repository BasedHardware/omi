"""
Python mapping for the dispatch library on macOS

This module does not contain docstrings for the wrapped code, check Apple's
documentation for details on how to use these functions.
"""


def _setup():
    import sys

    import Foundation
    import objc
    from . import _metadata
    from . import _dispatch
    from ._inlines import _inline_list_

    dir_func, getattr_func = objc.createFrameworkDirAndGetattr(
        name="dispatch",
        frameworkIdentifier=None,
        frameworkPath=None,
        globals_dict=globals(),
        inline_list=_inline_list_,
        parents=(_dispatch, Foundation),
        metadict=_metadata.__dict__,
    )

    globals()["__dir__"] = dir_func
    globals()["__getattr__"] = getattr_func

    del sys.modules["dispatch._metadata"]


globals().pop("_setup")()
