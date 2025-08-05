"""
Python <-> Objective-C bridge (PyObjC)

This module defines the core interfaces of the Python<->Objective-C bridge.
"""

__all__ = [
    "IBOutlet",
    "IBAction",
    "accessor",
    "Accessor",
    "typedAccessor",
    "callbackFor",
    "selectorFor",
    "synthesize",
    "namedselector",
    "typedSelector",
    "namedSelector",
    "instancemethod",
    "signature",
    "IBInspectable",
    "IB_DESIGNABLE",
    "callbackPointer",
]

import sys
import textwrap
import warnings

from objc._objc import (
    _C_ID,
    _C_NSBOOL,
    _C_SEL,
    _C_NSUInteger,
    _closurePointer,
    _makeClosure,
    ivar,
    selector,
)

from inspect import getfullargspec

_C_NSRange = [b"{_NSRange=II}", b"{_NSRange=QQ}"][sys.maxsize > 2**32]


#
# Interface builder support.
#
def IB_DESIGNABLE(cls):
    """
    Class decorator for annotating that a class can be used in Interface Builder.

    The decorator doesn't do anything.
    """
    return cls


def IBInspectable(prop):
    """
    Decorator for an Objective-C property to tell IB that the updated in IB.

    The decorator doesn't do anything
    """
    return prop


def IBOutlet(name=None):
    """
    Create an instance variable that can be used as an outlet in
    Interface Builder.
    """
    if name is None:
        return ivar(isOutlet=1)
    else:
        return ivar(name, isOutlet=1)


def IBAction(func):
    """
    Return an Objective-C method object that can be used as an action
    in Interface Builder.
    """
    if func is None:
        raise TypeError("IBAction argument must be a callable")
    return selector(func, signature=b"v@:@")


def instancemethod(func):
    if func is None:
        raise TypeError("instancemethod argument must be a callable")
    return selector(func, isClassMethod=False)


def accessor(func, typeSignature=b"@"):
    """
    Return an Objective-C method object that is conformant with key-value coding
    and key-value observing.
    """
    (
        args,
        varargs,
        varkw,
        defaults,
        kwonlyargs,
        _kwonlydefaults,
        _annotations,
    ) = getfullargspec(func)
    funcName = func.__name__
    maxArgs = len(args)
    minArgs = maxArgs - len(defaults or ())
    # implicit self
    selArgs = 1 + funcName.count("_")
    if varargs is not None or varkw is not None or kwonlyargs:
        raise TypeError(
            "%s can not be an accessor because it accepts varargs, varkw or kwonly"
            % (funcName,)
        )

    if not (minArgs <= selArgs <= maxArgs):
        if minArgs == maxArgs:
            raise TypeError(
                "%s expected to take %d args, but must accept %d "
                "from Objective-C (implicit self plus count of underscores)"
                % (funcName, maxArgs, selArgs)
            )
        else:
            raise TypeError(
                "%s expected to take between %d and %d args, but must accept %d "
                "from Objective-C (implicit self plus count of underscores)"
                % (funcName, minArgs, maxArgs, selArgs)
            )

    if selArgs == 3:
        if funcName.startswith("validate") and funcName.endswith("_error_"):
            return selector(func, signature=_C_NSBOOL + b"@:N^@o^@")

        if funcName.startswith("insertObject_in") and funcName.endswith("AtIndex_"):
            return selector(func, signature=b"v@:" + typeSignature + _C_NSUInteger)
        elif funcName.startswith("replaceObjectIn") and funcName.endswith(
            "AtIndex_withObject_"
        ):
            return selector(func, signature=b"v@:" + _C_NSUInteger + typeSignature)

        elif funcName.startswith("get") and funcName.endswith("_range_"):
            return selector(func, signature=b"v@:o^@" + _C_NSRange)

        elif funcName.startswith("insert") and funcName.endswith("_atIndexes_"):
            return selector(func, signature=b"v@:@@")

        elif funcName.startswith("replace") and "AtIndexes_with" in funcName:
            return selector(func, signature=b"v@:@@")

        # pass through to "too many arguments"

    elif selArgs == 2:
        if funcName.startswith("objectIn") and funcName.endswith("AtIndex_"):
            return selector(func, signature=typeSignature + b"@:" + _C_NSUInteger)
        elif funcName.startswith("removeObjectFrom") and funcName.endswith("AtIndex_"):
            return selector(func, signature=b"v@:" + _C_NSUInteger)
        elif funcName.startswith("remove") and funcName.endswith("AtIndexes_"):
            return selector(func, signature=b"v@:@")
        elif funcName.endswith("AtIndexes_"):
            return selector(func, signature=b"@@:@")
        elif funcName.startswith("memberOf"):
            return selector(func, signature=_C_NSBOOL + b"@:" + typeSignature)
        elif funcName.startswith("add") and funcName.endswith("Object_"):
            return selector(func, signature=b"v@:" + typeSignature)
        elif funcName.startswith("add"):
            return selector(func, signature=b"v@:@")
        elif funcName.startswith("intersect"):
            return selector(func, signature=b"v@:@")

        return selector(func, signature=b"v@:" + typeSignature)

    elif selArgs == 1:
        if funcName.startswith("countOf"):
            typeSignature = _C_NSUInteger
        elif funcName.startswith("enumerator"):
            typeSignature = b"@"

        return selector(func, signature=typeSignature + b"@:")

    raise TypeError(f"{funcName} not recognized as an accessor")


def typedSelector(signature):
    def _typedSelector(func):
        if func is None:
            raise TypeError("typedSelector() function argument must be a callable")
        if isinstance(func, classmethod):
            return selector(func.__func__, signature=signature, isClassMethod=True)

        return selector(func, signature=signature)

    return _typedSelector


def namedSelector(name, signature=None):
    """
    Decorator for overriding the Objective-C SEL for a method, usage:

        @namedSelector("foo:bar:")
        def foobar(self, foo, bar):
            return foo + bar
    """
    if signature is not None:

        def _namedselector(func):
            if func is None:
                raise TypeError("namedSelector argument must be a callable")
            if isinstance(func, classmethod):
                return selector(
                    func.__func__,
                    selector=name,
                    signature=signature,
                    isClassMethod=True,
                )
            return selector(func, selector=name, signature=signature)

    else:

        def _namedselector(func):
            if func is None:
                raise TypeError("namedSelector argument must be a callable")
            if isinstance(func, classmethod):
                return selector(
                    func.__func__,
                    selector=name,
                    isClassMethod=True,
                )
            return selector(func, selector=name)

    return _namedselector


def namedselector(name, signature=None):
    warnings.warn(
        "use objc.namedSelector instead of objc.namedselector",
        DeprecationWarning,
        stacklevel=2,
    )
    return namedSelector(name, signature)


def typedAccessor(typeSignature):
    """
    Decorator for creating a typed accessor, usage:

        @typedAccessor('i')
        def someIntegerAccessor(self):
            return self.someInteger

        @typedAccessor('i')
        def setSomeIntegerAccessor_(self, anInteger):
            self.someInteger = anInteger
    """

    def _typedAccessor(func):
        return accessor(func, typeSignature)

    return _typedAccessor


def Accessor(func):
    warnings.warn(
        "Use objc.accessor instead of objc.Accessor", DeprecationWarning, stacklevel=2
    )
    return accessor(func)


#
# Callback support
#
def callbackFor(callable, argIndex=-1):  # noqa: A002
    """
    Decorator for converting a function into an object that can be used
    as a callback function for (Objective-)C API's that take such a beast
    as one of their arguments.

    Note that using this decorator for methods is unsupported and that this
    decorator is optional when the callback isn't stored by the called function

    Usage::

        @objc.callbackFor(NSArray.sortedArrayUsingFunction_context_)
        def compare(left, right, context):
            return 1
    """

    def addClosure(function):
        closure, meta = _makeClosure(function, callable, argIndex)
        function.pyobjc_closure = closure
        function.__metadata__ = lambda: meta
        return function

    return addClosure


def callbackPointer(closure):
    """
    Return a value for "closure" that can be passed to a function
    expecting a "void *" argument.
    """
    if not hasattr(closure, "pyobjc_closure"):
        raise ValueError("Object is not decorated with 'callbackFor'")

    return _closurePointer(closure.pyobjc_closure)


def selectorFor(callable, argIndex=-1):  # noqa: A002
    """
    Decorator that makes sure that the method has the right signature to be
    used as the selector argument to the specified method.

    Usage::

        @objc.selectorFor(NSApplication.beginSheet_modalForWindow_modalDelegate_didEndSelector_contextInfo_)  # noqa: B950
        def sheetDidEnd_returnCode_contextInfo_(self, sheet, returnCode, info):
            pass
    """
    if argIndex == -1:
        for arg in callable.__metadata__()["arguments"]:
            if arg["type"] == _C_SEL and "sel_of_type" in arg:
                signature = arg["sel_of_type"]
                break
        else:
            raise ValueError("Not a selector argument with type information")

    else:
        try:
            signature = callable.__metadata__()["arguments"][argIndex]["sel_of_type"]
        except (IndexError, KeyError):
            raise ValueError("Not a selector argument with type information")

    def addSignature(function):
        return selector(function, signature=signature)

    return addSignature


def synthesize(
    name, copy=False, readwrite=True, type=_C_ID, ivarName=None  # noqa: A002
):
    """
    Use this in a class dictionary to syntheze simple setting/setter methods.

    Note: this is only necessary to get proper behaviour when Key-Value coding
    is used and special features (like copying) are needed

    usage::

        class MyClass (NSObject):
            objc.synthesize('someTitle', copy=True)

    """
    if not name:
        raise ValueError("Empty property name")

    if ivarName is None:
        ivarName = "_" + name

    classDict = sys._getframe(1).f_locals

    setterName = f"set{name[0].upper()}{name[1:]}_"

    if copy:
        setter = textwrap.dedent(
            """
            def %(name)s(self, value):
                self.%(ivar)s = value.copy()
            """
            % {"name": setterName, "ivar": ivarName}
        )

    else:
        setter = textwrap.dedent(
            """
            def %(name)s(self, value):
                self.%(ivar)s = value
            """
            % {"name": setterName, "ivar": ivarName}
        )

    getter = textwrap.dedent(
        """
            def %(name)s(self):
                return self.%(ivar)s
            """
        % {"name": name, "ivar": ivarName}
    )

    if readwrite:
        exec(setter, globals(), classDict)

    exec(getter, globals(), classDict)

    classDict[ivarName] = ivar(type=type)


def signature(signature, **kw):
    """
    A Python method decorator that allows easy specification
    of Objective-C selectors.

    Usage::

        @objc.signature('i@:if')
        def methodWithX_andY_(self, x, y):
            return 0
    """
    warnings.warn(
        "Usage objc.typedSelector instead of objc.signature",
        DeprecationWarning,
        stacklevel=2,
    )
    kw["signature"] = signature

    def makeSignature(func):
        return selector(func, **kw)

    return makeSignature
