"""
This module implements a callback function that is used by the C code to
add Python special methods to Objective-C classes with a suitable interface.
"""

from objc._objc import (
    _block_call,
    _rescanClass,
    currentBundle,
    lookUpClass,
    options,
    registerMetaDataForSelector,
    selector,
)
import PyObjCTools.KeyValueCoding as kvc
from objc._new import make_generic_new, NEW_MAP
from objc._transform import _selectorToKeywords

__all__ = (
    "addConvenienceForClass",
    "registerABCForClass",
    "registerUnavailableMethod",
    "registerNewKeywords",
    "registerNewKeywordsFromSelector",
)

CLASS_METHODS = {}
CLASS_ABC = {}


options._getKey = kvc.getKey
options._setKey = kvc.setKey
options._getKeyPath = kvc.getKeyPath
options._setKeyPath = kvc.setKeyPath

del kvc

for method in (
    b"alloc",
    b"copy",
    b"copyWithZone:",
    b"mutableCopy",
    b"mutableCopyWithZone:",
):
    registerMetaDataForSelector(
        b"NSObject", method, {"retval": {"already_retained": True}}
    )


def register(f):
    options._class_extender = f


@register
def add_convenience_methods(cls, type_dict):
    """
    Add additional methods to the type-dict of subclass 'name' of
    'super_class'.

    CLASS_METHODS is a global variable containing a mapping from
    class name to a list of Python method names and implementation.

    Matching entries from both mappings are added to the 'type_dict'.
    """

    # Only add the generic __new__ to pure ObjC classes,
    # __new__ will be added to Python subclasses by
    # ._transform.
    if not cls.__has_python_implementation__ and type(  # noqa: E721
        cls.__mro__[1].__new__
    ) != type(lambda: None):
        type_dict["__new__"] = make_generic_new(cls)

    for nm, value in CLASS_METHODS.get(cls.__name__, ()):
        type_dict[nm] = value

    try:
        for abc_class in CLASS_ABC[cls.__name__]:
            abc_class.register(cls)
        del CLASS_ABC[cls.__name__]
    except KeyError:
        pass


def register(f):
    options._make_bundleForClass = f


@register
def makeBundleForClass():
    cb = currentBundle()

    def bundleForClass(cls):
        return cb

    return selector(bundleForClass, isClassMethod=True)


def registerUnavailableMethod(classname, selector):
    """
    Mark *selector* as unavailable for *classname*.
    """
    if not isinstance(selector, bytes):
        raise TypeError("selector should by a bytes object")
    selname = selector.decode()

    # This adds None as a replacement value instead of
    # registering metadata because NS_UNAVAILABLE is
    # used to mark abstract base classes with concrete
    # public subclasses.
    # addConvenienceForClass(classname, ((selname.replace(":", "_"), None),))
    registerMetaDataForSelector(
        classname.encode(),
        selector,
        {"suggestion": f"{selector.decode()!r} is NS_UNAVAILABLE"},
    )

    if selname.startswith("init"):
        kw = _selectorToKeywords(selname)
        NEW_MAP.setdefault(classname, {})[kw] = None


def registerNewKeywordsFromSelector(classname, selector):
    """
    Register keywords calculated from 'selector' as passible
    keyword arguments for __new__ for the given class. The
    selector should be an 'init' method.
    """
    if not isinstance(selector, bytes):
        raise TypeError("selector should by a bytes object")
    selname = selector.decode()
    kw = _selectorToKeywords(selname)
    NEW_MAP.setdefault(classname, {})[kw] = selname.replace(":", "_")


def registerNewKeywords(classname, keywords, methodname):
    """
    Register the keyword tuple 'keywords' as a set of keyword
    arguments for __new__ for the given class that will result
    in the invocation of the given method.

    Method should be either an init method or a class method.
    """
    if not isinstance(keywords, tuple) or not all(isinstance(x, str) for x in keywords):
        raise TypeError("keywords must be tuple of strings")
    NEW_MAP.setdefault(classname, {})[keywords] = methodname


def registerABCForClass(classname, *abc_class):
    """
    Register *classname* with the *abc_class*-es when
    the class becomes available.
    """
    global CLASS_ABC
    try:
        CLASS_ABC[classname] += tuple(abc_class)
    except KeyError:
        CLASS_ABC[classname] = tuple(abc_class)

    options._mapping_count += 1
    _rescanClass(classname)


def addConvenienceForClass(classname, methods):
    """
    Add the list with methods to the class with the specified name
    """
    try:
        CLASS_METHODS[classname] += tuple(methods)
    except KeyError:
        CLASS_METHODS[classname] = tuple(methods)

    options._mapping_count += 1
    _rescanClass(classname)


#
# Helper functions for converting data item to/from a representation
# that is usable inside Cocoa data structures.
#
# In particular:
#
# - Python "None" is stored as +[NSNull null] because Cocoa containers
#   won't store NULL as a value (and this transformation is undone when
#   retrieving data)
#
# - When a getter returns NULL in Cocoa the queried value is not present,
#   that's converted to an exception in Python.
#

_NULL = lookUpClass("NSNull").null()


def container_wrap(v):
    if v is None:
        return _NULL
    return v


def container_unwrap(v, exc_type, *exc_args):
    if v is None:
        raise exc_type(*exc_args)
    elif v is _NULL:
        return None
    return v


#
#
# Misc. small helpers
#
#

addConvenienceForClass("NSNull", (("__bool__", lambda self: False),))

addConvenienceForClass(
    "NSEnumerator",
    (
        ("__iter__", lambda self: self),
        ("__next__", lambda self: container_unwrap(self.nextObject(), StopIteration)),
    ),
)


def __call__(self, *args, **kwds):
    return _block_call(self, self.__block_signature__, args, kwds)


addConvenienceForClass("NSBlock", (("__call__", __call__),))
