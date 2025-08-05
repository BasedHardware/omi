"""
Convenience interface for NSArray/NSMutableArray
"""

__all__ = ()

import collections.abc
import sys

from objc._convenience import addConvenienceForClass, container_unwrap, container_wrap
from objc._objc import _C_ID, _C_NSInteger
from objc._objc import _NSNotFound as NSNotFound
from objc._objc import lookUpClass, registerMetaDataForSelector
from ._new import NEW_MAP

NSArray = lookUpClass("NSArray")
NSMutableArray = lookUpClass("NSMutableArray")

collections.abc.Sequence.register(NSArray)
collections.abc.MutableSequence.register(NSMutableArray)


registerMetaDataForSelector(
    b"NSObject",
    b"sortUsingFunction:context:",
    {
        "arguments": {
            2: {
                "callable": {
                    "retval": {"type": _C_NSInteger},
                    "arguments": {
                        0: {"type": _C_ID},
                        1: {"type": _C_ID},
                        2: {"type": _C_ID},
                    },
                },
                "callable_retained": False,
            },
            3: {"type": _C_ID},
        }
    },
)


def _ensure_array(anArray):
    """Return *anArray* as a list, tuple or NSArray"""
    if not isinstance(anArray, (NSArray, list, tuple)):
        anArray = list(anArray)
    return anArray


def nsarray_reverse(self):
    """Reverse an array"""
    begin = 0
    end = len(self) - 1
    while begin < end:
        self.exchangeObjectAtIndex_withObjectAtIndex_(begin, end)
        begin += 1
        end -= 1


def nsarray_extend(self, anArray):
    for item in anArray:
        self.addObject_(container_wrap(item))


_index_sentinel = object()


def nsarray_index(self, item, start=0, stop=_index_sentinel):
    if start == 0 and stop is _index_sentinel:
        res = self.indexOfObject_(container_wrap(item))
        if res == NSNotFound:
            raise ValueError(f"{type(self).__name__}.index(x): x not in list")

    else:
        itemcount = self.count()
        if start < 0:
            start = itemcount + start
            if start < 0:
                start = 0

        if stop is not _index_sentinel:
            if stop < 0:
                stop = itemcount + stop
                if stop < 0:
                    stop = 0
        else:
            stop = itemcount

        if itemcount == 0:
            raise ValueError(f"{type(self).__name__}.index(x): x not in list")

        if start >= itemcount:
            raise ValueError(f"{type(self).__name__}.index(x): x not in list")

        if stop >= itemcount:
            stop = itemcount - 1

        if stop <= start:
            ln = 0

        else:
            ln = stop - start

        if ln == 0:
            raise ValueError(f"{type(self).__name__}.index(x): x not in list")

        if ln > sys.maxsize:  # pragma: no branch
            ln = sys.maxsize  # pragma: no cover

        res = self.indexOfObject_inRange_(item, (start, ln))
        if res == NSNotFound:
            raise ValueError(f"{type(self).__name__}.index(x): x not in list")

    return res


def nsarray_insert(self, idx, item):
    if idx < 0:
        idx += self.count()
        if idx < 0:
            idx = 0
    if idx >= self.count():
        self.addObject_(item)
        return
    self.insertObject_atIndex_(container_wrap(item), idx)


def nsarray__getitem__(self, idx):
    if isinstance(idx, slice):
        start, stop, step = idx.indices(len(self))
        return [self[i] for i in range(start, stop, step)]

    elif not isinstance(idx, int):
        raise TypeError("index must be a number")

    if idx < 0:
        idx += len(self)
        if idx < 0:
            raise IndexError("list index out of range")

    return container_unwrap(self.objectAtIndex_(idx), RuntimeError)


def nsarray__delitem__(self, idx):
    if isinstance(idx, slice):
        start, stop, step = idx.indices(self.count())
        if step == 1:
            if start > stop:
                # Nothing to remove
                return

            return self.removeObjectsInRange_((start, stop - start))

        r = reversed(range(start, stop, step))
        for i in r:
            self.removeObjectAtIndex_(i)
        return

    if idx < 0:
        idx += self.count()
        if idx < 0:
            raise IndexError("list index out of range")

    self.removeObjectAtIndex_(idx)


def nsarray_pop(self, idx=-1):
    length = self.count()
    if length <= 0:
        raise IndexError("pop from empty list")

    elif idx >= length or (idx + length) < 0:
        raise IndexError("pop index out of range")

    elif idx < 0:
        idx += len(self)

    rval = self.objectAtIndex_(idx)
    self.removeObjectAtIndex_(idx)
    return rval


def nsarray_remove(self, obj):
    idx = self.indexOfObject_(obj)
    if idx == NSNotFound:
        raise ValueError(f"{type(self).__name__}.remove(x): x not in list")
    self.removeObjectAtIndex_(idx)


index_error_message = "list indices must be integers or slices"


def nsarray__setitem__(self, idx, anObject):
    if isinstance(idx, slice):
        start, stop, step = idx.indices(self.count())
        if step >= 0:
            if stop <= start:
                # Empty slice: insert values
                stop = start

        anObject = _ensure_array(anObject)

        if step == 1:
            return self.replaceObjectsInRange_withObjectsFromArray_(
                (start, stop - start), anObject
            )

        slice_len = len(range(start, stop, step))
        if slice_len != len(anObject):
            raise ValueError(
                "Replacing extended slice with %d elements by %d elements"
                % (slice_len, len(anObject))
            )

        if step > 0:
            # NOTE: 'anObject' cannot be 'self' because assigning to an extended
            # slice cannot change the size of 'self' and slep 1 is handled earlier.
            toAssign = anObject

            for inIdx, outIdx in enumerate(range(start, stop, step)):
                self.replaceObjectAtIndex_withObject_(outIdx, toAssign[inIdx])

        # slice.indexes already catches this:
        # elif step == 0:
        #    raise ValueError("Step 0")

        else:
            if anObject is self:
                toAssign = list(anObject)
            else:
                toAssign = anObject

            for inIdx, outIdx in enumerate(range(start, stop, step)):
                self.replaceObjectAtIndex_withObject_(outIdx, toAssign[inIdx])

    elif not isinstance(idx, int):
        raise TypeError(index_error_message)

    else:
        if idx < 0:
            idx += self.count()
            if idx < 0:
                raise IndexError("list index out of range")

        self.replaceObjectAtIndex_withObject_(idx, anObject)


def nsarray_add(self, other):
    result = NSMutableArray(self)
    result.addObjectsFromArray_(_ensure_array(other))
    return result


def nsarray_radd(self, other):
    result = NSMutableArray(other)
    result.addObjectsFromArray_(self)
    return result


def nsarray_mul(self, other):
    """
    This tries to implement anNSArray * N
    somewhat efficiently (and definitely more
    efficient that repeated appending).
    """
    result = NSMutableArray.array()

    if other <= 0:
        return result

    n = 1
    tmp = self
    while other:
        if (other & n) != 0:
            result.addObjectsFromArray_(tmp)
            other -= n

        if other:
            n <<= 1
            tmp = tmp.arrayByAddingObjectsFromArray_(tmp)

    return result


def nsarray_new(cls, sequence=None):
    if not sequence:
        return NSArray.array()

    elif isinstance(sequence, str):
        return NSArray.arrayWithArray_(list(sequence))

    else:
        if not isinstance(sequence, (list, tuple)):
            return NSArray.arrayWithArray_(list(sequence))

        return NSArray.arrayWithArray_(sequence)


for cls in ("NSArray", "__NSArrayI", "__NSArrayM", "__NSArray0"):
    NEW_MAP.setdefault(cls, {})[()] = nsarray_new


def nsmutablearray_new(cls, sequence=None):
    if not sequence:
        return NSMutableArray.array()

    elif isinstance(sequence, str):
        return NSMutableArray.arrayWithArray_(list(sequence))

    else:
        if type(sequence) not in (list, tuple):
            return NSMutableArray.arrayWithArray_(list(sequence))

        # This is only valid when ``sequence`` is an built-in list or tuple,
        # otherwise arrayWithArray might access the sequence differently
        # then expected from a Python sequence initializer.
        return NSMutableArray.arrayWithArray_(sequence)


for cls in ("NSMutableArray",):
    d = NEW_MAP.setdefault(cls, {})
    d[()] = nsmutablearray_new


def nsarray__contains__(self, elem):
    return bool(self.containsObject_(container_wrap(elem)))


def nsarray_append(self, anObject):
    self.addObject_(container_wrap(anObject))


def nsarray_clear(self):
    self.removeAllObjects()


def nsarray_sort(self, key=lambda x: x, reverse=False):
    if reverse:

        def sort_func(a, b, _):
            a = key(a)
            b = key(b)
            if a < b:
                return 1

            elif b < a:
                return -1

            else:
                return 0

    else:

        def sort_func(a, b, _):
            a = key(a)
            b = key(b)

            if a < b:
                return -1
            elif b < a:
                return 1
            else:
                return 0

    self.sortUsingFunction_context_(sort_func, None)


def nsarray__len__(self):
    return self.count()


# NOTE: 'no cover' because all of the system array
# classes are subclasses of NSMutableArray.
def nsarray__copy__(self):  # pragma: no cover
    return self.copy()


def nsarray__iter__(self):
    return iter(self.objectEnumerator())


addConvenienceForClass(
    "NSArray",
    (
        ("__add__", nsarray_add),
        ("__radd__", nsarray_radd),
        ("__mul__", nsarray_mul),
        ("__rmul__", nsarray_mul),
        ("__len__", nsarray__len__),
        ("__contains__", nsarray__contains__),
        ("__getitem__", nsarray__getitem__),
        ("__copy__", nsarray__copy__),
        ("__iter__", nsarray__iter__),
        ("index", nsarray_index),
        ("remove", nsarray_remove),
        ("pop", nsarray_pop),
    ),
)

# See #334: Some part of Cocoa can load a category on subclasses of
# NSMutableArray that defines a pop method, which then interferes with
# nsarray_pop.
# The code below registers our own pop on all known subclasses of NSArray.
for cls in (
    "__NSArrayI",
    "__NSArrayM",
    "__NSArray0",
):
    addConvenienceForClass(
        cls,
        (("pop", nsarray_pop),),
    )


def nsmutablearray__copy__(self):
    return self.mutableCopy()


addConvenienceForClass(
    "NSMutableArray",
    (
        ("__copy__", nsmutablearray__copy__),
        ("__setitem__", nsarray__setitem__),
        ("__delitem__", nsarray__delitem__),
        ("extend", nsarray_extend),
        ("append", nsarray_append),
        ("sort", nsarray_sort),
        ("insert", nsarray_insert),
        ("reverse", nsarray_reverse),
        ("clear", nsarray_clear),
    ),
)
