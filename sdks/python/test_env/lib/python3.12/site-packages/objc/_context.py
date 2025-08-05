"""
A number of Cocoa API's have a 'context' argument that is a plain 'void*'
in ObjC, and an Integer value in Python.  The 'context' object defined here
allows you to get a unique integer number that can be used as the context
argument for any Python object, and retrieve that object later on using the
context number.

Usage::

    ...
    ctx = objc.context.register(myContext)
    someObject.observeValueForKeyPath_ofObject_change_context_(
        kp, obj, {}, ctx)
    ...

and in the callback::

    def observeValueForKeyPath_ofObject_change_context_(self,
        kp, obj, change, ctx):

        myContext = objc.context.get(ctx)
        ...

Use ``objc.context.unregister`` to remove the registration of ``myObject``
when you're done. The argument to unregister is the same object as was
passed in during registration.
"""

__all__ = ("context",)
from typing import Any


class ContextRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, value: Any) -> int:
        uniq = id(value)
        self._registry[uniq] = value
        return uniq

    def unregister(self, value: Any):
        try:
            del self._registry[id(value)]
        except KeyError:
            pass

    def get(self, uniq) -> Any:
        return self._registry[uniq]


context = ContextRegistry()
