"""
This module implements a callback function that is used by the C code to
add Python special methods to Objective-C classes with a suitable interface.
"""

from objc._convenience import addConvenienceForClass

__all__ = ("addConvenienceForBasicSequence",)


def seq_iter(self):
    for idx in range(len(self)):
        yield self[idx]


def seq_len(self):
    return self.count()


def seq_getitem(self, idx):
    if isinstance(idx, slice):
        raise ValueError("Slices not supported")

    if idx < 0:
        orig_idx = idx
        idx += seq_len(self)

        if idx < 0:
            raise IndexError(orig_idx)

    return self.objectAtIndex_(idx)


def seq_setitem(self, idx, value):
    if isinstance(idx, slice):
        raise ValueError("Slices not supported")

    if idx < 0:
        orig_idx = idx
        idx += seq_len(self)

        if idx < 0:
            raise IndexError(orig_idx)

    return self.setObject_atIndex_(value, idx)


def addConvenienceForBasicSequence(classname, readonly=True):
    addConvenienceForClass(
        classname,
        (("__len__", seq_len), ("__getitem__", seq_getitem), ("__iter__", seq_iter)),
    )

    if not readonly:
        addConvenienceForClass(classname, (("__setitem__", seq_setitem),))
