"""
Convenience methods for Cocoa mapping types.
"""

__all__ = ("addConvenienceForBasicMapping",)

import collections.abc

from objc._convenience import (
    CLASS_ABC,
    addConvenienceForClass,
    container_unwrap,
    container_wrap,
)


def __getitem__objectForKey_(self, key):
    res = self.objectForKey_(container_wrap(key))
    return container_unwrap(res, KeyError, key)


def get_objectForKey_(self, key, dflt=None):
    res = self.objectForKey_(container_wrap(key))
    if res is None:
        res = dflt
    return res


def contains_objectForKey_(self, key):
    res = self.objectForKey_(container_wrap(key))
    return res is not None


_CONVENIENCES_MAPPING_RO = (
    ("__getitem__", __getitem__objectForKey_),
    ("get", get_objectForKey_),
    ("__contains__", contains_objectForKey_),
)


def __delitem__removeObjectForKey_(self, key):
    self.removeObjectForKey_(container_wrap(key))


def update_setObject_forKey_(self, *args, **kwds):
    if len(args) == 0:
        pass
    elif len(args) != 1:
        raise TypeError(f"update expected at most 1 arguments, got {len(args)}")

    else:
        other = args[0]
        if hasattr(other, "keys"):
            # This mirrors the implementation of dict.update, but seems
            # wrong for Python3 (with collections.abc.Dict)
            for key in other.keys():
                self[key] = other[key]

        else:
            for key, value in other:
                self[key] = value

    for k in kwds:
        self[k] = kwds[k]


def setdefault_setObject_forKey_(self, key, dflt=None):
    try:
        return self[key]
    except KeyError:
        self[key] = dflt
        return dflt


def __setitem__setObject_forKey_(self, key, value):
    self.setObject_forKey_(container_wrap(value), container_wrap(key))


_pop_setObject_dflt = object()


def pop_setObject_forKey_(self, key, dflt=_pop_setObject_dflt):
    try:
        res = self[key]
    except KeyError:
        if dflt == _pop_setObject_dflt:
            raise KeyError(key)
        res = dflt
    else:
        del self[key]
    return res


def popitem_setObject_forKey_(self):
    try:
        it = self.keyEnumerator()
        k = container_unwrap(it.nextObject(), StopIteration)
    except (StopIteration, IndexError):
        raise KeyError(f"popitem on an empty {type(self).__name__}")
    else:
        result = (k, container_unwrap(self.objectForKey_(k), KeyError))
        self.removeObjectForKey_(k)
        return result


_CONVENIENCES_MAPPING_RW = _CONVENIENCES_MAPPING_RO + (
    ("__delitem__", __delitem__removeObjectForKey_),
    ("__setitem__", __setitem__setObject_forKey_),
    ("update", update_setObject_forKey_),
    ("setdefault", setdefault_setObject_forKey_),
    ("pop", pop_setObject_forKey_),
    ("popitem", popitem_setObject_forKey_),
)


def addConvenienceForBasicMapping(classname, readonly=True):
    """
    Add the convenience methods for a Cocoa mapping type

    Used to add the basic collections.abc.Mapping or collections.abc.MutableMapping
    APIs to a Cocoa class that has an API simular to NSDictionary.
    """
    addConvenienceForClass(
        classname, _CONVENIENCES_MAPPING_RO if readonly else _CONVENIENCES_MAPPING_RW
    )

    try:
        lst = CLASS_ABC[classname]
    except KeyError:
        lst = CLASS_ABC[classname] = []

    lst.append(collections.abc.Mapping if readonly else collections.abc.MutableMapping)
