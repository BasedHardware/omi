from objc import _objc

__all__ = []


class OC_PythonFloat(float):
    __slots__ = ("__pyobjc_object__",)

    def __new__(cls, obj, value):
        self = float.__new__(cls, value)
        self.__pyobjc_object__ = obj
        return self

    __class__ = property(lambda self: self.__pyobjc_object__.__class__)

    def __getattr__(self, attr):
        return getattr(self.__pyobjc_object__, attr)

    def __reduce__(self):
        return (float, (float(self),))


class OC_PythonLong(int):
    def __new__(cls, obj, value):
        self = int.__new__(cls, value)
        self.__pyobjc_object__ = obj
        return self

    __class__ = property(lambda self: self.__pyobjc_object__.__class__)

    def __getattr__(self, attr):
        return getattr(self.__pyobjc_object__, attr)

    # The long type doesn't support __slots__ on subclasses, fake
    # one part of the effect of __slots__: don't allow setting of attributes.
    def __setattr__(self, attr, value):
        if attr != "__pyobjc_object__":
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{attr}')"
            )
        self.__dict__["__pyobjc_object__"] = value

    def __reduce__(self):
        return (int, (int(self),))


NSNumber = _objc.lookUpClass("NSNumber")
NSDecimalNumber = _objc.lookUpClass("NSDecimalNumber")


def numberWrapper(obj):
    if isinstance(obj, NSDecimalNumber):
        return obj

    try:
        tp = obj.objCType()
    except AttributeError:
        import warnings

        warnings.warn(
            f"NSNumber instance doesn't implement objCType? {obj!r}",
            RuntimeWarning,
            stacklevel=2,
        )
        return obj

    if tp in b"qQLfd":
        if tp == b"q":
            return OC_PythonLong(obj, obj.longLongValue())
        elif tp in b"QL":
            return OC_PythonLong(obj, obj.unsignedLongLongValue())
        else:
            return OC_PythonFloat(obj, obj.doubleValue())
    else:
        return OC_PythonLong(obj, obj.longValue())


_objc.options._nsnumber_wrapper = numberWrapper
