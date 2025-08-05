import objc
import functools
import sys


def _structConvenience(structname, structencoding):
    def makevar(cls, name=None):
        if name is None:
            return objc.ivar(type=structencoding)
        else:
            return objc.ivar(name=name, type=structencoding)

    makevar.__name__ = structname
    makevar.__doc__ = f"Create *ivar* for type encoding {structencoding!r}"
    if hasattr(objc.ivar, "__qualname__"):  # pragma: no branch
        makevar.__qualname__ = objc.ivar.__qualname__ + "." + structname

    setattr(objc.ivar, sys.intern(structname), classmethod(makevar))


# Fake it for basic C types
_structConvenience("bool", objc._C_BOOL)
_structConvenience("char", objc._C_CHR)
_structConvenience("int", objc._C_INT)
_structConvenience("short", objc._C_SHT)
_structConvenience("long", objc._C_LNG)
_structConvenience("long_long", objc._C_LNG_LNG)
_structConvenience("unsigned_char", objc._C_UCHR)
_structConvenience("unsigned_int", objc._C_UINT)
_structConvenience("unsigned_short", objc._C_USHT)
_structConvenience("unsigned_long", objc._C_ULNG)
_structConvenience("unsigned_long_long", objc._C_ULNG_LNG)
_structConvenience("float", objc._C_FLT)
_structConvenience("double", objc._C_DBL)
_structConvenience("BOOL", objc._C_NSBOOL)
_structConvenience("UniChar", objc._C_UNICHAR)
_structConvenience("char_text", objc._C_CHAR_AS_TEXT)
_structConvenience("char_int", objc._C_CHAR_AS_INT)

_orig_createStructType = objc.createStructType


@functools.wraps(objc.createStructType)
def createStructType(name, typestr, fieldnames, doc=None, pack=-1):
    result = _orig_createStructType(name, typestr, fieldnames, doc, pack)
    _structConvenience(name, result.__typestr__)
    return result


objc.createStructType = createStructType


_orig_registerStructAlias = objc.registerStructAlias


@functools.wraps(objc.registerStructAlias)
def registerStructAlias(typestr, structType):
    return _orig_registerStructAlias(typestr, structType)


def createStructAlias(name, typestr, structType):
    result = _orig_registerStructAlias(typestr, structType)
    _structConvenience(name, result.__typestr__)
    return result


objc.createStructAlias = createStructAlias
objc.registerStructAlias = registerStructAlias
