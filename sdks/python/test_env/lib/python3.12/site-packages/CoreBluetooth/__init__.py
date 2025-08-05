"""
Python mapping for the CloudKit framework.

This module does not contain docstrings for the wrapped code, check Apple's
documentation for details on how to use these functions and classes.
"""


def _setup():
    import sys

    import Foundation
    import objc
    from . import _metadata, _CoreBluetooth

    dir_func, getattr_func = objc.createFrameworkDirAndGetattr(
        name="CoreBluetooth",
        frameworkIdentifier="com.apple.CoreBluetooth",
        frameworkPath=objc.pathForFramework(
            "/System/Library/Frameworks/CoreBluetooth.framework"
        ),
        globals_dict=globals(),
        inline_list=None,
        parents=(
            _CoreBluetooth,
            Foundation,
        ),
        metadict=_metadata.__dict__,
    )

    globals()["__dir__"] = dir_func
    globals()["__getattr__"] = getattr_func

    for cls, sel in (
        ("CBManager", b"init"),
        ("CBPeer", b"init"),
        ("CBATTRequest", b"init"),
        ("CBAttribute", b"init"),
    ):
        objc.registerUnavailableMethod(cls, sel)

    del sys.modules["CoreBluetooth._metadata"]


globals().pop("_setup")()
