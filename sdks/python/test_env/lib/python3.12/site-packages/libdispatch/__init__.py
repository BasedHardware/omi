"""
Python mapping for the dispatch library on macOS

This module does not contain docstrings for the wrapped code, check Apple's
documentation for details on how to use these functions.
"""


def _setup():
    import dispatch
    import objc

    dir_func, getattr_func = objc.createFrameworkDirAndGetattr(
        name="libdispatch",
        frameworkIdentifier=None,
        frameworkPath=None,
        globals_dict=globals(),
        inline_list=None,
        parents=(dispatch,),
        metadict={},
    )

    globals()["__dir__"] = dir_func
    globals()["__getattr__"] = getattr_func


globals().pop("_setup")()
