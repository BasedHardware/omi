"""
Helper module that is used by objc_class.setattr and objc_class.__new__
to transform class attributes and process the class dictionary (for the
latter).

The C code relies on this code to do most semantic checks, and only
performs checks that are needed to avoid crashes.
"""

import objc
import types
import inspect
import dis
import keyword
import warnings
import sys
from ._informal_protocol import _informal_protocol_for_selector
from . import _new

# only public objc_method until the python_method implementation
# in C is gone
__all__ = ("objc_method", "python_method")


NO_VALUE = object()


def _isSelectorPrefix(name, prefix):
    return name.startswith(prefix) and (
        len(name) == len(prefix) | name[len(prefix)].isupper()
    )


def _selectorToKeywords(selector):
    if not selector.startswith("init"):
        raise ValueError("selector is not a valid init selector")
    if len(selector) > 4 and not selector[4].isupper():
        raise ValueError("selector is a valid init selector")
    selector = selector[4:]
    if not selector:
        return ()

    parts = selector.split(":")[:-1]
    if parts[0].startswith("With"):
        parts[0] = parts[0][4:]

    if len(parts[0]) == 1 or (len(parts[0]) > 1 and not parts[0].isupper()):
        parts[0] = parts[0][:1].lower() + parts[0][1:]

    return tuple(parts)


def setDunderNew(
    class_object,
):
    class_object.__new__ = _new.make_generic_new(class_object)


def processClassDict(
    class_name,
    class_dict,
    meta_dict,
    class_object,
    protocols,
    hidden_instance_methods,
    hidden_class_methods,
):
    """
    First step into creating a subclass for a Cocoa class:

    - Transform attributes
    - Return (instance_variablees, instanstance_methods, class_methods)
    """
    instance_variables = {}
    instance_methods = set()
    class_methods = set()

    for p in protocols:
        if not isinstance(p, (objc.formal_protocol, objc.informal_protocol)):
            raise TypeError(
                "protocols list contains object that isn't an Objective-C "
                f"protocol, but type {type(p).__name__}"
            )

    if "__classcell__" in class_dict and "__module__" in class_dict:
        mod = sys.modules.get(class_dict["__module__"], None)
        if mod is not None:
            try:
                ok = mod.super is objc.super
            except AttributeError:
                ok = False

            if not ok:
                warnings.warn(
                    "Objective-C subclass uses super(), but super is not objc.super",
                    category=objc.ObjCSuperWarning,
                    stacklevel=2,
                )

    super_ivars = set()
    for v in class_object.__dict__.values():
        if isinstance(v, objc.ivar):
            super_ivars.add(v.__name__)

    class_dict["__objc_python_subclass__"] = True
    process_slots(class_dict, instance_variables, class_object)

    # First call all class setup hooks. Those can
    # update the class dictiory, which is why this
    # loop cannot be merged into the next one.
    for key, value in list(class_dict.items()):
        setup = getattr(value, "__pyobjc_class_setup__", NO_VALUE)
        if setup is not NO_VALUE:
            setup(key, class_dict, instance_methods, class_methods)

    for key, value in list(class_dict.items()):
        old_value = value
        new_value = transformAttribute(key, value, class_object, protocols)
        if new_value is not value:
            class_dict[key] = new_value
            value = new_value

        if isinstance(value, objc.selector):
            if isinstance(old_value, python_method):
                continue

        if isinstance(value, objc.selector):
            canonical = value.selector.decode().replace(":", "_")

            if value.isClassMethod:
                del class_dict[key]
                if not value.isHidden:
                    meta_dict[key] = value
                    if canonical != key:
                        meta_dict[canonical] = value

                class_methods.add(value)
            else:
                if value.isHidden:
                    del class_dict[key]
                elif canonical != key:
                    class_dict[canonical] = value

                instance_methods.add(value)

        elif isinstance(value, objc.ivar):
            if value.__name__ in instance_variables:
                raise objc.error(f"{key!r} reimplements objc.ivar {value.__name__!r}")
            if value.__name__ in super_ivars:
                raise objc.error(
                    f"objc.ivar {key!r} overrides instance variable in super class"
                )
            instance_variables[value.__name__] = value

    # Convert the collections to tuples for easier
    # post-processing in the C code.
    #
    # The results are sorted for easier testing, this should
    # be harmless because classes tend to be fairly simple.
    instance_variables = tuple(
        sorted(instance_variables.values(), key=lambda x: x.__name__)
    )
    instance_methods = tuple(
        sorted(
            instance_methods,
            key=lambda x: x.selector if isinstance(x, objc.selector) else x,
        )
    )
    class_methods = tuple(
        sorted(
            class_methods,
            key=lambda x: x.selector if isinstance(x, objc.selector) else x,
        )
    )

    validate_protocols(class_object, instance_methods, class_methods, protocols)

    for sel in instance_methods:
        if isinstance(sel, bytes):
            hidden_instance_methods[sel] = None
        elif sel.isHidden:
            hidden_instance_methods[sel.selector] = sel

    for sel in class_methods:
        if isinstance(sel, bytes):
            hidden_class_methods[sel] = None
        elif sel.isHidden:
            hidden_class_methods[sel.selector] = sel

    new_kw_map = {}

    for name, value in class_dict.items():
        if not isinstance(name, str) or not name.startswith("init"):
            continue
        if len(name) > 4 and not name[4].isupper():
            continue
        if value is None and name == "init":
            new_kw_map[()] = None
            continue
        elif not isinstance(value, objc.selector):
            continue

        new_kw_map[_selectorToKeywords(value.selector.decode())] = name
    if new_kw_map:
        _new.NEW_MAP[class_name] = new_kw_map

    return (
        instance_variables,
        instance_methods,
        class_methods,
        # Either __new__ in this class, or a custom new in a parent class
        ("__new__" in class_dict)
        or type(class_object.__new__) == type(lambda: 1),  # noqa: E721
    )


def validate_protocols(class_object, instance_methods, class_methods, protocols):
    instance_map = {
        sel.selector: sel for sel in instance_methods if isinstance(sel, objc.selector)
    }
    class_map = {
        sel.selector: sel for sel in class_methods if isinstance(sel, objc.selector)
    }

    for proto in protocols:
        for is_class_method, method_list in [
            (False, proto.instanceMethods()),
            (True, proto.classMethods()),
        ]:
            for sel in method_list:
                if is_class_method:
                    found = class_map.get(sel["selector"], None)
                    if found is None:
                        found = getattr(
                            class_object.pyobjc_classMethods,
                            sel["selector"].decode().replace(":", "_"),
                            None,
                        )
                else:
                    found = instance_map.get(sel["selector"], None)
                    if found is None:
                        found = getattr(
                            class_object.pyobjc_instanceMethods,
                            sel["selector"].decode().replace(":", "_"),
                            None,
                        )

                if found is None:
                    if sel["required"]:
                        raise TypeError(
                            f"class does not fully implemented protocol {proto.__name__!r}: "
                            "no implementation for "
                            f"{'class' if is_class_method else 'instance'} method "
                            f"{sel['selector'].decode()!r}"
                        )
                    continue

                if sel["typestr"] != found.signature:
                    raise TypeError(
                        f"class does not correctly implement protocol {proto.__name__!r}: "
                        f"the signature for method {sel['selector'].decode()} is "
                        f"{found.signature.decode()!r} instead of {sel['typestr'].decode()!r}"
                    )


def process_slots(class_dict, instance_variables, class_object):
    """
    Process the ``__slots__`` attribute, if any.
    """
    slots = class_dict.get("__slots__", NO_VALUE)
    if slots is NO_VALUE:
        if not class_object.__hasdict__:
            instance_variables["__dict__"] = objc.ivar(
                "__dict__", objc._C_PythonObject, isSlot=True
            )
    else:
        if isinstance(slots, str):
            if slots in class_dict:
                raise objc.error(f"slot {slots!r} redefines {class_dict[slots]!r}")

            class_dict[slots] = objc.ivar(slots, objc._C_PythonObject, isSlot=True)

        else:
            for nm in slots:
                if nm in class_dict:
                    raise objc.error(f"slot {nm!r} redefines {class_dict[nm]!r}")

                class_dict[nm] = objc.ivar(nm, objc._C_PythonObject, isSlot=True)

    class_dict["__slots__"] = ()


def transformAttribute(name, value, class_object, protocols):
    """
    Transform 'value' before it will be added to a class

    For callables this will convert the value to an
    'objc.selector' object where appropriate, other values
    are returned as-is.
    """
    if not callable(value) and not isinstance(value, classmethod):
        return value
    elif isinstance(value, (objc.native_selector, staticmethod, type)):
        return value
    elif isinstance(value, objc.selector):
        if value.callable is None:
            raise ValueError(f"{name!r}: selector object without callable")
        return objc.selector(
            value.callable,
            value.selector,
            value.signature,
            isClassMethod=value.isClassMethod,
            isRequired=value.isRequired,
            isHidden=value.isHidden,
        )
    elif is_generator_or_async(value):
        return value
    elif isinstance(value, python_method):
        return value.__wrapped__

    isclass = None

    if not isinstance(name, str):
        selname = None
    else:
        selname = default_selector(name)
    signature = None

    if selname is not None and isinstance(class_object, objc.objc_class):
        registered = objc._registeredMetadataForSelector(class_object, selname)
    else:
        registered = None

    if selname in {b"copy", b"copyWithZone:", b"mutableCopy", b"mutableCopyWithZone:"}:
        # Specials: NSObject defines copy and copyWithZone as class methods,
        # while most users would expect to define an instance method.
        isclass = False
    helper_signature = NO_VALUE

    # DWIM: Copy classmethod-ness and signature from
    # a pre-existing method on the class, but prefer
    # using an instance method over a class method, as
    # this makes it a lot easier to implement methods from
    # the NSObject protocol (amongst others)
    if isinstance(name, str) and helper_signature is NO_VALUE:
        current = getattr(class_object.pyobjc_instanceMethods, name, NO_VALUE)
        if current is NO_VALUE:
            current = getattr(class_object.pyobjc_classMethods, name, NO_VALUE)
        if isinstance(current, objc.selector):
            if isclass is None:
                isclass = current.isClassMethod
            # ishidden = current.isHidden
            signature = current.signature
            selname = current.selector

    if isinstance(value, classmethod):
        # Unwrap "classmethod" instances.
        # XXX: Switch to __wrapped__ when support for 3.9 is dropped
        value = value.__func__
        isclass = True

        if isinstance(value, python_method):
            # Deal with:
            #   @classmethod
            #   @python_method
            #   def ...
            #
            return classmethod(value.__wrapped__)

        assert not isinstance(value, classmethod)

    if isinstance(value, objc_method):
        # Unwrap "objc_method" instances
        if value.isclass is not None:
            isclass = value.isclass

        if value.selector is not None:
            selname = value.selector
            registered = objc._registeredMetadataForSelector(class_object, selname)

        if value.signature is not None:
            signature = value.signature
            registered = None

        if selname is None:
            raise ValueError(
                f"{name!r} is an objc_method instance, but cannot determine Objective-C selector"
            )

        if isinstance(value.__wrapped__, classmethod):
            # Deal with:
            #    @objc_method
            #    @classsmethod
            #    def ...
            #
            if value.isclass is not None:
                raise ValueError(
                    f"{name!r} is objc_method with isclass specified wraps classmethod"
                )
            isclass = True

            # XXX switch from __func__ to __wrapped-__ when support
            # for 3.9 ends.
            value = value.__wrapped__.__func__
        else:
            value = value.__wrapped__

    if registered and "full_signature" in registered:
        signature = registered["full_signature"]

    if selname is None:
        # The 'name' does not fit into the selector naming
        # convention, and nothing provided a better name.
        #
        # Assume this is meant to be a regular python method.
        if not isinstance(name, str):
            raise TypeError(
                f"method name is of type {type(name).__name__}, not a string"
            )
        if isclass:
            return classmethod(value)
        return value

    argcount = selname.count(b":")

    if signature is None:
        # Look for the signature in an informal protocol when it
        # isn't set by some other means.
        informal = _informal_protocol_for_selector(selname)
        if informal is not None:
            for meth in informal.selectors:
                if meth.selector == selname:
                    if isclass is not None and meth.isClassMethod != isclass:
                        # "classmethod"-ness was explicitly set (inherit,
                        # classmethod, or objc_method), ignore the informal
                        # protocol if it doesn't match.
                        continue

                    signature = meth.signature
                    isclass = meth.isClassMethod

    if isclass is None:
        isclass = False

    if signature is None and protocols:
        for prot in protocols:
            if isclass:
                info = prot.descriptionForClassMethod_(selname)
            else:
                info = prot.descriptionForInstanceMethod_(selname)
        if info is not None:
            signature = info[1]

    if signature is None:
        # Calculate a default signature based on the selector shape
        if isinstance(value, (types.FunctionType, types.MethodType)):
            returns_object = returns_value(value)
        else:
            returns_object = True

        signature = (
            (objc._C_ID if returns_object else objc._C_VOID)
            + objc._C_ID
            + objc._C_SEL
            + (objc._C_ID * argcount)
        )

        if registered:
            overridden_rval = (
                registered["retval"].get("type", None)
                if registered["retval"] is not None
                else None
            )
            overridden_args = {}
            for idx, a in enumerate(registered["arguments"]):
                if a and "type" in a:
                    overridden_args[idx] = a["type"]

            if overridden_rval or overridden_args:
                signature_parts = list(objc.splitSignature(signature))
                if overridden_rval:
                    signature_parts[0] = overridden_rval

                for idx in overridden_args:
                    if (idx < 0) or idx >= len(signature_parts) - 1:
                        raise objc.error(
                            f"{name!r} has invalid metadata, index {idx} out of range"
                        )
                    signature_parts[idx + 1] = overridden_args[idx]
                signature = b"".join(signature_parts)

    # All information for creating a selector is available, do a
    # last consistency check.
    try:
        pysig = inspect.signature(value)
    except (AttributeError, ValueError, TypeError):
        pass
    else:
        pos = 0
        pos_default = 0
        kwonly = 0
        kwonly_default = 0
        has_var_pos = False

        for p in pysig.parameters.values():
            if p.kind == inspect.Parameter.KEYWORD_ONLY:
                kwonly += 1
                if p.default is not inspect.Parameter.empty:
                    kwonly_default += 1

            elif p.kind == inspect.Parameter.VAR_KEYWORD:
                pass

            elif p.kind == inspect.Parameter.VAR_POSITIONAL:
                has_var_pos = True

            else:
                pos += 1
                if p.default is not inspect.Parameter.empty:
                    pos_default += 1

        if kwonly - kwonly_default:
            # Calls from Obejctive-C to Python will never have keyword arguments,
            # therefore this callable is not compatible with use as a selector.
            raise objc.BadPrototypeError(
                f"{value!r} has {kwonly - kwonly_default} keyword-only arguments without a default"
            )

        if not has_var_pos and (
            (pos < argcount + 1) or (pos - pos_default > argcount + 1)
        ):
            # 'value' does not have a '*arg' argument, and does not accept calls
            # with exactly 'argcount' arguments, therefore this callable is not
            # compatible with us as a selector.
            #
            # 'argcount' does not count the implicit self argument
            if pos_default:
                raise objc.BadPrototypeError(
                    f"{selname.decode()!r} expects {argcount} arguments, "
                    f"{value!r} has between {pos-pos_default-1} and {pos-1} positional arguments"
                )
            else:
                raise objc.BadPrototypeError(
                    f"{selname.decode()!r} expects {argcount} arguments, "
                    f"{value!r} has {pos-1} positional arguments"
                )

    # XXX: This is needed because SomeClass.pyobjc_instanceMethods.hiddenSelector.isHidden
    #      is false :-(
    ishidden = False
    for cls in class_object.mro():  # pragma: no branch
        if not issubclass(cls, objc.objc_object):
            # Skip all non-objc class in the MRO to ignore
            # mixin classes.
            continue
        if selname in cls.pyobjc_hiddenSelectors(isclass):
            ishidden = True
            break

    return objc.selector(
        value, selname, signature, isClassMethod=isclass, isHidden=ishidden
    )


def is_generator_or_async(value):
    """
    Returns true for generators and async functions
    """
    # This guard is there to deal with some edge-case testing the
    # PyObjC test suite, should never trigger in production code.
    if not isinstance(value, types.FunctionType):
        return False
    if not isinstance(value.__code__, types.CodeType):
        return False

    if inspect.iscoroutine(value) or inspect.iscoroutinefunction(value):
        return True
    elif inspect.isgenerator(value) or inspect.isgeneratorfunction(value):
        return True
    return False


def returns_value(func):
    """
    Return True if 'func' explicitly returns a value

    """
    # This will return False for functions where all explicit
    # returns are of the form "return" or "return None". The
    # latter is a false negative, but cannot be avoided with
    # bytecode inspection.
    # XXX: This will give a false positive for functions
    #      that only contain "return None" paths for
    #      returning a value.
    if not isinstance(func.__code__, types.CodeType):
        return True

    prev = None

    for inst in dis.get_instructions(func):
        if inst.opname == "RETURN_VALUE":
            assert prev is not None
            if prev.opname == "LOAD_CONST" and prev.arg != 0:
                return True
            elif prev.opname != "LOAD_CONST":
                return True

        elif inst.opname == "RETURN_CONST" and inst.arg != 0:
            # New in Python 3.12.
            return True
        prev = inst

    return False


def default_selector(name):
    """
    Returns a byte string with the selector for 'name',
    or None if there is no default selector
    """
    if name.endswith("__") and keyword.iskeyword(name[:-2]):
        name = name[:-2]
    if name.startswith("__") and name.endswith("__"):
        return None

    if "_" in name[1:] and not name.endswith("_"):
        return None
    value = name.replace("_", ":").encode()
    if value.startswith(b":"):
        value = b"_" + value[1:]
    return value


class objc_method:
    """
    Decorator that marks a method that should definitely
    be represented as an Objective-C selector

    This decorator can be used in two ways:

    - Without parens:

        @objc_method
        def someMethod(self): ...

    - With parens:

        @objc_method()
        def someMethod(self): ...

    In the second form a number of keyword-only arguments can
    be used:

    - selname [bytes]: Objective-C selector name for the method
    - signature [bytes]: Objective-C type encoding for the method
    - isclass [bool]: Determines if the value is a class method

    When these attributes are not provided they will be calculated
    from the context (name, callable, class to which this
    method is added)
    """

    __slots__ = ("__wrapped__", "selector", "signature", "isclass")

    def __init__(self, value=None, *, selector=None, signature=None, isclass=None):
        self.__wrapped__ = value
        if self.__wrapped__ is not None:
            if not callable(self.__wrapped__) and not isinstance(
                self.__wrapped__, classmethod
            ):
                raise TypeError("'value' is not a callable")

        self.selector = selector
        self.signature = signature
        self.isclass = isclass

    def __call__(self, *args, **kwds):
        if self.__wrapped__ is None:
            if len(kwds) != 0:
                raise TypeError("Unexpected keyword arguments")
            if len(args) != 1:
                raise TypeError("Expecting exactly 1 argument")
            self.__wrapped__ = args[0]
            if not callable(self.__wrapped__) and not isinstance(
                self.__wrapped__, classmethod
            ):
                raise TypeError("'value' is not a callable")
            return self

        return self.__wrapped__(*args, **kwds)


class python_method:
    """
    Decorator that marks a method that should definitely
    not be represented as an Objective-C selector

    This decorator can be used in two ways:

    - Without parens:

        @python_method
        def someMethod(self): ...

    - With parens:

        @python_method()
        def someMethod(self): ...

    The second form has no keyword arguments and is
    provided for compatibility with objc_method.
    """

    __slots__ = ("__wrapped__",)

    def __init__(self, value=None):
        self.__wrapped__ = value
        if self.__wrapped__ is not None:
            if not callable(self.__wrapped__) and not isinstance(
                self.__wrapped__, classmethod
            ):
                raise TypeError(f"{value!r} is not a callable")

    def __get__(self, instance, owner):
        return self.__wrapped__.__get__(instance, owner)

    def __call__(self, *args, **kwds):
        if self.__wrapped__ is None:
            if len(kwds) != 0:
                raise TypeError("Unexpected keyword arguments")
            if len(args) != 1:
                raise TypeError("Expecting exactly 1 argument")
            self.__wrapped__ = args[0]
            if not callable(self.__wrapped__) and not isinstance(
                self.__wrapped__, classmethod
            ):
                raise TypeError("'value' is not a callable")
            return self

        return self.__wrapped__(*args, **kwds)

    @property
    def callable(self):  # noqa: A003
        # Compatibility with older version of PyObjC
        warnings.warn(
            "python_method.callable is deprecated, use __wrapped__ instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.__wrapped__


objc.options._transformAttribute = transformAttribute
objc.options._processClassDict = processClassDict
objc.options._setDunderNew = setDunderNew
