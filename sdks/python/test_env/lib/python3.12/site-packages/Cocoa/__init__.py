"""
Python mapping for the Cocoa framework.

This module does not contain docstrings for the wrapped code, check Apple's
documentation for details on how to use these functions and classes.
"""


def _setup():
    import AppKit
    import objc

    dir_func, getattr_func = objc.createFrameworkDirAndGetattr(
        name="Cocoa",
        frameworkIdentifier=None,
        frameworkPath=None,
        globals_dict=globals(),
        inline_list=None,
        parents=(AppKit,),
        metadict={},
    )

    globals()["__dir__"] = dir_func
    globals()["__getattr__"] = getattr_func


globals().pop("_setup")()
