"""
Convenience interface for NSString
"""

from objc._convenience import addConvenienceForClass
from ._new import NEW_MAP

__all__ = ()

_no_value = object()


def nsstring_new(cls, value=_no_value):
    if value is _no_value:
        return cls.alloc().init()
    else:
        return cls.alloc().initWithString_(value)


for cls in ("NSString", "NSMutableString"):
    NEW_MAP.setdefault(cls, {})[()] = nsstring_new

addConvenienceForClass(
    "NSString",
    (
        ("__len__", lambda self: self.length()),
        ("endswith", lambda self, pfx: self.hasSuffix_(pfx)),
        ("startswith", lambda self, pfx: self.hasPrefix_(pfx)),
    ),
)
