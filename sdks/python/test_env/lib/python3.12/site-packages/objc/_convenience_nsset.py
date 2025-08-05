"""
Convenience interface for NSSet/NSMutableSet
"""

__all__ = ()

import collections.abc

from objc._convenience import addConvenienceForClass, container_unwrap, container_wrap
from objc._objc import lookUpClass
from ._new import NEW_MAP

NSSet = lookUpClass("NSSet")
NSMutableSet = lookUpClass("NSMutableSet")

collections.abc.Set.register(NSSet)
collections.abc.MutableSet.register(NSMutableSet)


def nsset_isdisjoint(self, other):
    if not hasattr(other, "__contains__"):
        other = list(other)

    for item in self:
        if item in other:
            return False
    return True


def nsset_union(self, *other):
    result = NSMutableSet()
    result.unionSet_(self)
    for val in other:
        if isinstance(val, collections.abc.Set):
            result.unionSet_(val)
        else:
            result.unionSet_(set(val))
    return result


def nsset_intersection(self, *others):
    if len(others) == 0:
        return self.mutableCopy()

    others = [o if hasattr(o, "__contains__") else list(o) for o in others]

    result = NSMutableSet()
    for item in self:
        for o in others:
            if item not in o:
                break
        else:
            result.add(item)
    return result


def nsset_difference(self, *others):
    result = self.mutableCopy()

    for value in others:
        if isinstance(value, collections.abc.Set):
            result.minusSet_(value)
        else:
            result.minusSet_(set(value))

    return result


def nsset_symmetric_difference(self, other):
    result = NSMutableSet()
    if not hasattr(other, "__contains__"):
        other = list(other)
    for item in iter(self):
        if item not in other:
            result.add(item)
    for item in other:
        if item not in self:
            result.add(item)
    return result


def nsset__contains__(self, value):
    hash(value)  # Force error for non-hashable values
    return self.containsObject_(value)


def nsset__or__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("NSSet|value where value is not a set")
    return nsset_union(self, other)


def nsset__ror__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("value|NSSet where value is not a set")
    return nsset_union(other, self)


def nsset__and__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("NSSet&value where value is not a set")
    return nsset_intersection(self, other)


def nsset__rand__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("value&NSSet where value is not a set")
    return nsset_intersection(other, self)


def nsset__sub__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("NSSet-value where value is not a set")
    return nsset_difference(self, other)


def nsset__rsub__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("NSSet-value where value is not a set")
    return nsset_difference(NSMutableSet(other), self)


def nsset__xor__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError("NSSet-value where value is not a set")
    return nsset_symmetric_difference(other, self)


def nsset_issubset(self, other):
    if isinstance(other, collections.abc.Set):
        return self.isSubsetOfSet_(other)

    else:
        return self.isSubsetOfSet_(set(other))


def nsset__le__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError()
    return nsset_issubset(self, other)


def nsset__eq__(self, other):
    if not isinstance(other, collections.abc.Set):
        return False

    return self.isEqualToSet_(other)


def nsset__ne__(self, other):
    if not isinstance(other, collections.abc.Set):
        return True

    return not self.isEqualToSet_(other)


def nsset__lt__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError()

    return (self <= other) and (self != other)


def nsset_issuperset(self, other):
    if not isinstance(other, collections.abc.Set):
        other = set(other)

    for item in other:
        if item not in self:
            return False

    return True


def nsset__ge__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError()
    return nsset_issuperset(self, other)


def nsset__gt__(self, other):
    if not isinstance(other, collections.abc.Set):
        raise TypeError()
    return (self >= other) and (self != other)


def nsset_update(self, *others):
    for other in others:
        if isinstance(other, collections.abc.Set):
            self.unionSet_(other)
        else:
            self.unionSet_(set(other))


def nsset_intersection_update(self, *others):
    for other in others:
        if isinstance(other, collections.abc.Set):
            self.intersectSet_(other)
        else:
            self.intersectSet_(set(other))


def nsset_difference_update(self, *others):
    for other in others:
        if isinstance(other, collections.abc.Set):
            self.minusSet_(other)
        else:
            self.minusSet_(set(other))


def nsset_symmetric_difference_update(self, other):
    toadd = set()
    toremove = set()

    if isinstance(other, collections.abc.Set):
        totest = other
    else:
        totest = set(other)

    for value in self:
        if value in totest:
            toremove.add(value)
    for value in totest:
        if value not in self:
            toadd.add(value)

    self.minusSet_(toremove)
    self.unionSet_(toadd)


def nsset_pop(self):
    if len(self) == 0:
        raise KeyError()

    v = self.anyObject()
    self.removeObject_(v)
    return container_unwrap(v, KeyError)


def nsset_remove(self, value):
    hash(value)
    value = container_wrap(value)
    if value not in self:
        raise KeyError(value)
    self.removeObject_(value)


def nsset_discard(self, value):
    hash(value)
    self.removeObject_(container_wrap(value))


def nsset_add(self, value):
    hash(value)
    self.addObject_(container_wrap(value))


class nsset__iter__:
    def __init__(self, value):
        self._size = len(value)
        self._enum = value.objectEnumerator()

    def __length_hint__(self):
        return self._size

    def __iter__(self):
        return self

    def __next__(self):
        self._size -= 1
        return container_unwrap(self._enum.nextObject(), StopIteration)


addConvenienceForClass(
    "NSSet",
    (
        ("__len__", lambda self: self.count()),
        ("__iter__", lambda self: nsset__iter__(self)),
        ("__contains__", nsset__contains__),
        ("isdisjoint", nsset_isdisjoint),
        ("union", nsset_union),
        ("intersection", nsset_intersection),
        ("difference", nsset_difference),
        ("symmetric_difference", nsset_symmetric_difference),
        ("issubset", nsset_issubset),
        ("__eq__", nsset__eq__),
        ("__ne__", nsset__ne__),
        ("__le__", nsset__le__),
        ("__lt__", nsset__lt__),
        ("issuperset", nsset_issuperset),
        ("__ge__", nsset__ge__),
        ("__gt__", nsset__gt__),
        ("__or__", nsset__or__),
        ("__ror__", nsset__ror__),
        ("__and__", nsset__and__),
        ("__rand__", nsset__rand__),
        ("__xor__", nsset__xor__),
        ("__rxor__", nsset__xor__),
        ("__sub__", nsset__sub__),
        ("__rsub__", nsset__rsub__),
    ),
)

addConvenienceForClass(
    "NSMutableSet",
    (
        ("add", nsset_add),
        ("remove", nsset_remove),
        ("discard", nsset_discard),
        ("update", nsset_update),
        ("intersection_update", nsset_intersection_update),
        ("difference_update", nsset_difference_update),
        ("symmetric_difference_update", nsset_symmetric_difference_update),
        ("clear", lambda self: self.removeAllObjects()),
        ("pop", nsset_pop),
    ),
)


def nsset_new(cls, sequence=None):
    if not sequence:
        return NSSet.set()

    if isinstance(sequence, (NSSet, set, frozenset)):
        return NSSet.set().setByAddingObjectsFromSet_(sequence)

    else:
        return NSSet.set().setByAddingObjectsFromSet_(set(sequence))


def nsmutableset_new(cls, sequence=None):
    if not sequence:
        value = NSMutableSet.set()

    elif isinstance(sequence, (NSSet, set, frozenset)):
        value = NSMutableSet.set()
        value.unionSet_(sequence)

    else:
        value = NSMutableSet.set()
        value.unionSet_(set(sequence))

    return value


NEW_MAP.setdefault("NSSet", {})[()] = nsset_new
NEW_MAP.setdefault("NSMutableSet", {})[()] = nsmutableset_new
