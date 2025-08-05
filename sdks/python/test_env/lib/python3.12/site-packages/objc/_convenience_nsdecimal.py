"""
Support for NSDecimalNumber.

The actual class is defined in Foundation, but having the wrapper
here is much more convenient.
"""

__all__ = ()
import operator

from objc._convenience import addConvenienceForClass
from objc._objc import NSDecimal, lookUpClass
from ._new import NEW_MAP

NSDecimalNumber = lookUpClass("NSDecimalNumber")


def decimal_new(cls, value=None):
    if value is None:
        return cls.numberWithInt_(0)

    else:
        if isinstance(value, NSDecimal):
            return cls.decimalNumberWithDecimal_(value)
        elif isinstance(value, NSDecimalNumber):
            return cls.decimalNumberWithDecimal_(value.decimalValue())
        elif isinstance(value, float):
            return cls.numberWithDouble_(value)
        elif isinstance(value, str):
            value = NSDecimal(value)
            return cls.decimalNumberWithDecimal_(value)
        else:
            # The value is either an integer, or
            # invalid (and numberWithLongLong_ will raise
            # TypeError)
            try:
                return cls.numberWithLongLong_(value)

            except ValueError:
                raise TypeError("Value is not a number")


NEW_MAP.setdefault("NSDecimalNumber", {})[()] = decimal_new

addConvenienceForClass(
    "NSDecimalNumber",
    (
        (
            "__add__",
            lambda self, other: NSDecimalNumber(operator.add(NSDecimal(self), other)),
        ),
        (
            "__radd__",
            lambda self, other: NSDecimalNumber(operator.add(other, NSDecimal(self))),
        ),
        (
            "__sub__",
            lambda self, other: NSDecimalNumber(operator.sub(NSDecimal(self), other)),
        ),
        (
            "__rsub__",
            lambda self, other: NSDecimalNumber(operator.sub(other, NSDecimal(self))),
        ),
        (
            "__mul__",
            lambda self, other: NSDecimalNumber(operator.mul(NSDecimal(self), other)),
        ),
        (
            "__rmul__",
            lambda self, other: NSDecimalNumber(operator.mul(other, NSDecimal(self))),
        ),
        (
            "__truediv__",
            lambda self, other: NSDecimalNumber(
                operator.truediv(NSDecimal(self), other)
            ),
        ),
        (
            "__rtruediv__",
            lambda self, other: NSDecimalNumber(
                operator.truediv(other, NSDecimal(self))
            ),
        ),
        (
            "__floordiv__",
            lambda self, other: NSDecimalNumber(
                operator.floordiv(NSDecimal(self), other)
            ),
        ),
        (
            "__rfloordiv__",
            lambda self, other: NSDecimalNumber(
                operator.floordiv(other, NSDecimal(self))
            ),
        ),
        (
            "__mod__",
            lambda self, other: NSDecimalNumber(operator.mod(NSDecimal(self), other)),
        ),
        (
            "__rmod__",
            lambda self, other: NSDecimalNumber(operator.mod(other, NSDecimal(self))),
        ),
        ("__neg__", lambda self: NSDecimalNumber(operator.neg(NSDecimal(self)))),
        ("__pos__", lambda self: NSDecimalNumber(operator.pos(NSDecimal(self)))),
        ("__abs__", lambda self: NSDecimalNumber(abs(NSDecimal(self)))),
        ("__lt__", lambda self, other: (NSDecimal(self) < other)),
        ("__gt__", lambda self, other: (NSDecimal(self) > other)),
        ("__le__", lambda self, other: (NSDecimal(self) <= other)),
        ("__ge__", lambda self, other: (NSDecimal(self) >= other)),
        ("__eq__", lambda self, other: (NSDecimal(self) == other)),
        ("__ne__", lambda self, other: (NSDecimal(self) != other)),
    ),
)

addConvenienceForClass(
    "NSDecimalNumber",
    (("__round__", lambda self, n=0: NSDecimalNumber(round(NSDecimal(self), n))),),
)
