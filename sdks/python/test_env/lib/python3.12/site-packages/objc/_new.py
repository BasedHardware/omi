"""
Implementation of `__new__` for arbitrary Cocoa classes

The __new__ method just translates invocations into the
corresponding invocation of the Cocoa pattern (
`cls.alloc().init()` or `cls.new()`), based on a mapping
maintaind in this file.

The mapping is updated in two ways:
    1. From framework bindings for native classes
    2. Based on `init` methods in Python subclasses

"""

import objc

__all__ = ()

# Mapping: class name -> { kwds: selector_name }
#
# That is, keys are names of Objective-C classes, values
# are mappings from keyword argument names to
# the name of a selector.
#
# The selector_name can be `None` to disable a
# mapping in a subclass.
#
# The complete mapping for a class is a chain map
# for the submaps of all classes on the MRO.
NEW_MAP = {
    "NSObject": {(): "init"},
}

# Sentinel value
UNSET = object()

# Added to the docstring for __new__
DOC_SUFFIX = "The order of keyword arguments is significant\n"


def calculate_new_doc(cls):
    """
    Calculate the docstring for the __new__
    for *cls*
    """
    result = {}
    for c in reversed(cls.__mro__):
        new_map = NEW_MAP.get(c.__name__, UNSET)
        if new_map is UNSET:
            continue

        for kwds, selector in new_map.items():
            if selector is None:
                result.pop(kwds, None)

            if not kwds:
                result[kwds] = f"{cls.__name__}(): "
            else:
                result[kwds] = f"{cls.__name__}(*, " + ", ".join(kwds) + "): "
            if selector.startswith("init"):
                result[
                    kwds
                ] += f"\n   returns cls.alloc().{selector}({', '.join(kwds)})\n\n"
            else:
                result[kwds] += f"\n   returns cls.{selector}({', '.join(kwds)})\n\n"
    return "".join(sorted(result.values())) + DOC_SUFFIX


class function_wrapper:
    """
    Wrapper for the __new__ function to generate the
    docstring dynamically.
    """

    __slots__ = ("_function", "_cls")

    def __init__(self, function, cls):
        self._function = function
        self._cls = cls

    @property
    def __class__(self):
        return self._function.__class__

    @property
    def __doc__(self):
        return calculate_new_doc(self._cls)

    def __getattr__(self, name):
        return getattr(self._function, name)

    def __setattr__(self, name, value):
        if name in ("_function", "_cls"):
            object.__setattr__(self, name, value)
        return setattr(self._function, name, value)

    def __call__(self, *args, **kwds):
        return self._function(*args, **kwds)


def make_generic_new(cls):
    def __new__(cls, *args, **kwds):
        """
        Generic implementation for Objective-C `__new__`.
        """
        key = tuple(kwds.keys())

        for c in cls.__mro__:
            new_map = NEW_MAP.get(c.__name__, UNSET)
            if new_map is UNSET:
                continue

            name = new_map.get(key, UNSET)
            if name is UNSET:
                continue

            if name is None:
                if key:
                    raise TypeError(
                        f"{cls.__name__}() does not support keyword arguments {', '.join(repr(k) for k in key)}"
                    )
                else:
                    raise TypeError(f"{cls.__name__}() requires keyword arguments")

            if not isinstance(name, str):
                # Assume that 'name' is actually a callable.
                #
                # This is used to implement custom signatures for a number
                # of classes in the various ._convenience sibling modules.
                return name(cls, *args, **kwds)

            if args:
                raise TypeError(
                    f"{cls.__name__}() does not accept positional arguments"
                )

            args = [kwds[n] for n in key]
            if name.startswith("init") and len(name) == 4 or name[4].isupper():
                return getattr(cls.alloc(), name)(*args)

            else:
                return getattr(cls, name)(*args)

        if key in (("cobject",), ("c_void_p",)):
            # Support for creating instances from raw pointers in the default
            # __new__ implementation.
            return objc.objc_object.__new__(cls, **kwds)

        if key:
            raise TypeError(
                f"{cls.__name__}() does not support keyword arguments {', '.join(repr(k) for k in key)}"
            )
        else:
            raise TypeError(f"{cls.__name__}() requires keyword arguments")

    # XXX: Settings these helps, but does not yet result in the correct
    #      output from help()
    __new__.__name__ = cls.__name__ + ".__new__"
    __new__.__qualname__ = cls.__name__ + ".__new__"
    __new__.__module__ = cls.__module__
    return function_wrapper(__new__, cls)


objc.options._genericNewClass = function_wrapper
