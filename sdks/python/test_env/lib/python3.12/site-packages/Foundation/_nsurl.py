"""
Helpers for NSURL
"""

import sys
import objc


def __fspath__(self):
    if self.scheme() == "file":
        # self.fileSystemRepresentation returns a byte string,
        # whereas most user code expects regular strings. Decode
        # in the same way as extension functions in the ``os`` module.
        return self.fileSystemRepresentation().decode(
            sys.getfilesystemencoding(), sys.getfilesystemencodeerrors()
        )

    raise TypeError(f"NSURL with scheme {self.scheme()!r} instead of 'file'")


objc.addConvenienceForClass(
    "NSURL",
    (("__fspath__", __fspath__),),
)
