"""
Python mapping for the CoreFoundation framework.

This module does not contain docstrings for the wrapped code, check Apple's
documentation for details on how to use these functions and classes.
"""


def _setup():
    import sys

    import objc
    from . import _metadata, _CoreFoundation, _static
    from ._inlines import _inline_list_

    dir_func, getattr_func = objc.createFrameworkDirAndGetattr(
        name="CoreFoundation",
        frameworkIdentifier="com.apple.CoreFoundation",
        frameworkPath=objc.pathForFramework(
            "/System/Library/Frameworks/CoreFoundation.framework"
        ),
        globals_dict=globals(),
        inline_list=_inline_list_,
        parents=(
            _CoreFoundation,
            _static,
        ),
        metadict=_metadata.__dict__,
    )

    globals()["__dir__"] = dir_func
    globals()["__getattr__"] = getattr_func

    del sys.modules["CoreFoundation._metadata"]


globals().pop("_setup")()
