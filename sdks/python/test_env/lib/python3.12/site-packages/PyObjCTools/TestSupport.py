"""
Helper code for implementing unittests.

This module is unsupported and is primairily used in the PyObjC
testsuite.
"""

import contextlib
import gc as _gc
import os as _os
import re as _re
import struct as _struct
import sys as _sys
import unittest as _unittest
import subprocess as _subprocess
import pickle as _pickle
from sysconfig import get_config_var as _get_config_var

import objc


# Ensure that methods in this module get filtered in the tracebacks
# from unittest
__unittest = False

# Have a way to disable the autorelease pool behaviour
_usepool = not _os.environ.get("PYOBJC_NO_AUTORELEASE")

# XXX: Python 2 Compatibility for the PyObjC Test Suite
try:
    unicode
except NameError:
    unicode = str

try:
    long
except NameError:
    long = int

try:
    basestring
except NameError:
    basestring = str

try:
    unichr
except NameError:
    unichr = chr


def _typemap(tp):
    if tp is None:
        return None
    return (
        tp.replace(b"_NSRect", b"CGRect")
        .replace(b"_NSPoint", b"CGPoint")
        .replace(b"_NSSize", b"CGSize")
    )


@contextlib.contextmanager
def pyobjc_options(**kwds):
    orig = {}
    try:
        for k in kwds:
            orig[k] = getattr(objc.options, k)
            setattr(objc.options, k, kwds[k])

        yield

    finally:
        for k in orig:
            setattr(objc.options, k, orig[k])


def sdkForPython(_cache=[]):  # noqa: B006, M511
    """
    Return the SDK version used to compile Python itself,
    or None if no framework was used
    """
    if not _cache:
        cflags = _get_config_var("CFLAGS")
        m = _re.search(r"-isysroot\s+([^ ]*)(\s|$)", cflags)
        if m is None:
            _cache.append(None)
            return None

        path = m.group(1)
        if path == "/":
            result = tuple(map(int, os_release().split(".")))
            _cache.append(result)
            return result

        bn = _os.path.basename(path)
        version = bn[6:-4]
        if version.endswith("u"):
            version = version[:-1]

        result = tuple(map(int, version.split(".")))
        _cache.append(result)
        return result

    return _cache[0]


def fourcc(v):
    """
    Decode four-character-code integer definition

    (e.g. 'abcd')
    """
    return _struct.unpack(">i", v)[0]


def cast_int(value):
    """
    Cast value to 32bit integer

    Usage:
        cast_int(1 << 31) == -1

    (where as: 1 << 31 == 2147483648)
    """
    value = value & 0xFFFFFFFF
    if value & 0x80000000:
        value = ~value + 1 & 0xFFFFFFFF
        return -value
    else:
        return value


def cast_longlong(value):
    """
    Cast value to 64bit integer

    Usage:
        cast_longlong(1 << 63) == -1
    """
    value = value & 0xFFFFFFFFFFFFFFFF
    if value & 0x8000000000000000:
        value = ~value + 1 & 0xFFFFFFFFFFFFFFFF
        return -value
    else:
        return value


def cast_uint(value):
    """
    Cast value to 32bit integer

    Usage:
        cast_int(1 << 31) == 2147483648

    """
    value = value & 0xFFFFFFFF
    return value


def cast_ulonglong(value):
    """
    Cast value to 64bit integer
    """
    value = value & 0xFFFFFFFFFFFFFFFF
    return value


_os_release = None


def os_release():
    """
    Returns the release of macOS (for example 10.5.1).
    """
    global _os_release
    if _os_release is not None:
        return _os_release

    _os_release = (
        _subprocess.check_output(["sw_vers", "-productVersion"]).decode().strip()
    )

    return _os_release


def arch_only(arch):
    """
    Usage::
        class Tests (unittest.TestCase):

            @arch_only("arm64")
            def testArm64(self):
                pass

    The test runs only when the specified architecture matches
    """

    def decorator(function):
        return _unittest.skipUnless(objc.arch == arch, f"{arch} only")(function)

    return decorator


def min_python_release(version):
    """
    Usage::

        class Tests (unittest.TestCase):

            @min_python_release('3.2')
            def test_python_3_2(self):
                pass
    """
    parts = tuple(map(int, version.split(".")))
    return _unittest.skipUnless(
        _sys.version_info[:2] >= parts, f"Requires Python {version} or later"
    )


def _sort_key(version):
    parts = version.split(".")
    if len(parts) == 2:
        parts.append("0")

    if len(parts) != 3:
        raise ValueError(f"Invalid version: {version!r}")

    return tuple(int(x) for x in parts)


def os_level_key(release):
    """
    Return an object that can be used to compare two releases.
    """
    return _sort_key(release)


def min_sdk_level(release):
    """
    Usage::

        class Tests (unittest.TestCase):
            @min_sdk_level('10.6')
            def testSnowLeopardSDK(self):
                pass
    """
    v = (objc.PyObjC_BUILD_RELEASE // 100, objc.PyObjC_BUILD_RELEASE % 100, 0)
    return _unittest.skipUnless(
        v >= os_level_key(release), f"Requires build with SDK {release} or later"
    )


def max_sdk_level(release):
    """
    Usage::

        class Tests (unittest.TestCase):
            @max_sdk_level('10.5')
            def testUntilLeopardSDK(self):
                pass
    """
    v = (objc.PyObjC_BUILD_RELEASE // 100, objc.PyObjC_BUILD_RELEASE % 100, 0)
    return _unittest.skipUnless(
        v <= os_level_key(release), f"Requires build with SDK {release} or later"
    )


def min_os_level(release):
    """
    Usage::

        class Tests (unittest.TestCase):

            @min_os_level('10.6')
            def testSnowLeopardCode(self):
                pass
    """
    return _unittest.skipUnless(
        os_level_key(os_release()) >= os_level_key(release),
        f"Requires macOS {release} or later",
    )


def max_os_level(release):
    """
    Usage::

        class Tests (unittest.TestCase):

            @max_os_level('10.5')
            def testUntilLeopard(self):
                pass
    """
    return _unittest.skipUnless(
        os_level_key(os_release()) <= os_level_key(release),
        f"Requires macOS up to {release}",
    )


def os_level_between(min_release, max_release):
    """
    Usage::

        class Tests (unittest.TestCase):

            @os_level_between('10.5', '10.8')
            def testUntilLeopard(self):
                pass
    """
    return _unittest.skipUnless(
        os_level_key(min_release)
        <= os_level_key(os_release())
        <= os_level_key(max_release),
        f"Requires macOS {min_release} up to {max_release}",
    )


_poolclass = objc.lookUpClass("NSAutoreleasePool")

# NOTE: On at least macOS 10.8 there are multiple proxy classes for CFTypeRef...
_nscftype = tuple(cls for cls in objc.getClassList(1) if "NSCFType" in cls.__name__)

_typealias = {}

_typealias[objc._C_LNG_LNG] = objc._C_LNG
_typealias[objc._C_ULNG_LNG] = objc._C_ULNG

_idlike_cache = set()


class TestCase(_unittest.TestCase):
    """
    A version of TestCase that wraps every test into its own
    autorelease pool.

    This also adds a number of useful assertion methods
    """

    # New API for testing function/method signatures, with one assert for
    # the callable and one assert each for every return value and argument.
    #
    # Primary reason for the new API is to ensure that all metadata overrides
    # are explicitly tested.

    def assertManualBinding(self, func):
        if hasattr(func, "__metadata__"):
            self.fail(f"{func} has automatic bindings")

    def assertIsCFType(self, tp, message=None):
        if not isinstance(tp, objc.objc_class):
            self.fail(message or f"{tp!r} is not a CFTypeRef type")

        if any(x is tp for x in _nscftype):
            self.fail(message or f"{tp!r} is not a unique CFTypeRef type")

        for cls in tp.__bases__:
            if "NSCFType" in cls.__name__:
                return

        self.fail(message or f"{tp!r} is not a CFTypeRef type")

        # NOTE: Don't test if this is a subclass of one of the known
        #       CF roots, this tests is mostly used to ensure that the
        #       type is distinct from one of those roots.
        # NOTE: With the next two lines enabled there are spurious test
        #       failures when a CF type is toll-free bridged to an
        #       (undocumented) Cocoa class. It might be worthwhile to
        #       look for these, but not in the test suite.
        # if not issubclass(tp, _nscftype):
        #    self.fail(message or "%r is not a CFTypeRef subclass"%(tp,))

    def assertIsEnumType(self, tp):
        if not hasattr(tp, "__supertype__"):
            # Ducktyping for compatibility with Python 3.7
            # or earlier.
            self.fail(f"{tp!r} is not a typing.NewType")

        if tp.__supertype__ != int:
            self.fail(f"{tp!r} is not a typing.NewType based on 'int'")

    def assertIsTypedEnum(self, tp, base):
        if not hasattr(tp, "__supertype__"):
            # Ducktyping for compatibility with Python 3.7
            # or earlier.
            self.fail(f"{tp!r} is not a typing.NewType")

        if tp.__supertype__ != base:
            self.fail(f"{tp!r} is not a typing.NewType based on {base.__name__!r}")

    def assertIsOpaquePointer(self, tp, message=None):
        if not hasattr(tp, "__pointer__"):
            self.fail(message or f"{tp!r} is not an opaque-pointer")

        if not hasattr(tp, "__typestr__"):
            self.fail(message or f"{tp!r} is not an opaque-pointer")

    def assertResultIsNullTerminated(self, method, message=None):
        info = method.__metadata__()
        if not info.get("retval", {}).get("c_array_delimited_by_null"):
            self.fail(message or f"result of {method!r} is not a null-terminated array")

    def assertIsNullTerminated(self, method, message=None):
        info = method.__metadata__()
        if not info.get("c_array_delimited_by_null") or not info.get("variadic"):
            self.fail(
                message
                or "%s is not a variadic function with a "
                "null-terminated list of arguments" % (method,)
            )

    def assertArgIsIDLike(self, method, argno, message=None):
        global _idlike_cache

        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        tp = info["arguments"][argno + offset].get("type")

        if tp in {b"@", b"^@", b"n^@", b"N^@", b"o^@"}:
            return

        if tp in _idlike_cache:
            return
        elif tp.startswith(b"^") and tp[1:] in _idlike_cache:
            return
        elif tp.startswith(b"o^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"n^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"N^") and tp[2:] in _idlike_cache:
            return

        # Assume that tests are supposed to pass,
        # our cache may be out of date
        tmp = set(objc._idSignatures())
        _idlike_cache = set(tmp)

        if tp in _idlike_cache:
            return
        elif tp.startswith(b"^") and tp[1:] in _idlike_cache:
            return
        elif tp.startswith(b"o^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"n^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"N^") and tp[2:] in _idlike_cache:
            return

        self.fail(
            message or "argument %d of %r is not IDLike (%r)" % (argno, method, tp)
        )

    def assertResultIsIDLike(self, method, message=None):
        global _idlike_cache

        info = method.__metadata__()
        tp = info["retval"].get("type")

        if tp in {b"@", b"^@", b"n^@", b"N^@", b"o^@"}:
            return

        if tp in _idlike_cache:
            return
        elif tp.startswith(b"^") and tp[1:] in _idlike_cache:
            return
        elif tp.startswith(b"o^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"n^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"N^") and tp[2:] in _idlike_cache:
            return

        # Assume that tests are supposed to pass,
        # our cache may be out of date
        tmp = set(objc._idSignatures())
        _idlike_cache = set(tmp)

        if tp in _idlike_cache:
            return
        elif tp.startswith(b"^") and tp[1:] in _idlike_cache:
            return
        elif tp.startswith(b"o^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"n^") and tp[2:] in _idlike_cache:
            return
        elif tp.startswith(b"N^") and tp[2:] in _idlike_cache:
            return

        self.fail(message or f"result of {method!r} is not IDLike ({tp!r})")

    def assertArgIsNullTerminated(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            if not info["arguments"][argno + offset].get("c_array_delimited_by_null"):
                self.fail(
                    message
                    or "argument %d of %r is not a null-terminated array"
                    % (argno, method)
                )
        except (KeyError, IndexError):
            self.fail(
                message
                or "argument %d of %r is not a null-terminated array" % (argno, method)
            )

    def assertArgIsVariableSize(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            if not info["arguments"][argno + offset].get("c_array_of_variable_length"):
                self.fail(
                    message
                    or "argument %d of %r is not a variable sized array"
                    % (argno, method)
                )
        except (KeyError, IndexError):
            self.fail(
                message
                or "argument %d of %r is not a variable sized array" % (argno, method)
            )

    def assertResultIsVariableSize(self, method, message=None):
        info = method.__metadata__()
        if not info.get("retval", {}).get("c_array_of_variable_length", False):
            self.fail(message or f"result of {method!r} is not a variable sized array")

    def assertArgSizeInResult(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            if not info["arguments"][argno + offset].get("c_array_length_in_result"):
                self.fail(
                    message
                    or "argument %d of %r does not have size in result"
                    % (argno, method)
                )
        except (KeyError, IndexError):
            self.fail(
                message
                or "argument %d of %r does not have size in result" % (argno, method)
            )

    def assertArgIsPrintf(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        if not info.get("variadic"):
            self.fail(message or f"{method!r} is not a variadic function")

        try:
            if not info["arguments"][argno + offset].get("printf_format"):
                self.fail(
                    message
                    or "%r argument %d is not a printf format string" % (method, argno)
                )
        except (KeyError, IndexError):
            self.fail(
                message
                or "%r argument %d is not a printf format string" % (method, argno)
            )

    def assertArgIsCFRetained(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()

        try:
            if not info["arguments"][argno + offset]["already_cfretained"]:
                self.fail(
                    message or f"Argument {argno} of {method!r} is not cfretained"
                )
        except (KeyError, IndexError):
            self.fail(message or f"Argument {argno} of {method!r} is not cfretained")

    def assertArgIsNotCFRetained(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            if info["arguments"][argno + offset]["already_cfretained"]:
                self.fail(message or f"Argument {argno} of {method!r} is cfretained")
        except (KeyError, IndexError):
            pass

    def assertResultIsCFRetained(self, method, message=None):
        info = method.__metadata__()

        if not info.get("retval", {}).get("already_cfretained", False):
            self.fail(message or f"{method!r} is not cfretained")

    def assertResultIsNotCFRetained(self, method, message=None):
        info = method.__metadata__()
        if info.get("retval", {}).get("already_cfretained", False):
            self.fail(message or f"{method!r} is cfretained")

    def assertArgIsRetained(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()

        try:
            if not info["arguments"][argno + offset]["already_retained"]:
                self.fail(message or f"Argument {argno} of {method!r} is not retained")
        except (KeyError, IndexError):
            self.fail(message or f"Argument {argno} of {method!r} is not retained")

    def assertArgIsNotRetained(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            if info["arguments"][argno + offset]["already_retained"]:
                self.fail(message or f"Argument {argno} of {method!r} is retained")
        except (KeyError, IndexError):
            pass

    def assertResultIsRetained(self, method, message=None):
        info = method.__metadata__()
        if not info.get("retval", {}).get("already_retained", False):
            self.fail(message or f"Result of {method!r} is not retained")

    def assertResultIsNotRetained(self, method, message=None):
        info = method.__metadata__()
        if info.get("retval", {}).get("already_retained", False):
            self.fail(message or f"Result of {method!r} is retained")

    def assertResultHasType(self, method, tp, message=None):
        info = method.__metadata__()
        typestr = info.get("retval").get("type", b"v")
        if (
            typestr != tp
            and _typemap(typestr) != _typemap(tp)
            and _typealias.get(typestr, typestr) != _typealias.get(tp, tp)
        ):
            self.fail(
                message
                or f"result of {method!r} is not of type {tp!r}, but {typestr!r}"
            )

    def assertArgHasType(self, method, argno, tp, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            i = info["arguments"][argno + offset]

        except (KeyError, IndexError):
            self.fail(
                message
                or "arg %d of %s has no metadata (or doesn't exist)" % (argno, method)
            )

        else:
            typestr = i.get("type", b"@")

        if (
            typestr != tp
            and _typemap(typestr) != _typemap(tp)
            and _typealias.get(typestr, typestr) != _typealias.get(tp, tp)
        ):
            self.fail(
                message
                or "arg %d of %s is not of type %r, but %r"
                % (argno, method, tp, typestr)
            )

    def assertArgIsFunction(self, method, argno, sel_type, retained, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()

        try:
            i = info["arguments"][argno + offset]
        except (KeyError, IndexError):
            self.fail(
                message
                or "arg %d of %s has no metadata (or doesn't exist)" % (argno, method)
            )

        else:
            typestr = i.get("type", b"@")

        if typestr != b"^?":
            self.fail(
                message
                or "arg %d of %s is not of type function_pointer" % (argno, method)
            )

        st = i.get("callable")
        if st is None:
            self.fail(
                message
                or "arg %d of %s is not of type function_pointer" % (argno, method)
            )

        try:
            iface = st["retval"]["type"]
            for a in st["arguments"]:
                iface += a["type"]
        except KeyError:
            self.fail(
                message
                or "arg %d of %s is a function pointer with incomplete type information"
                % (argno, method)
            )

        if iface != sel_type:
            self.fail(
                message
                or "arg %d of %s is not a function_pointer with type %r, but %r"
                % (argno, method, sel_type, iface)
            )

        st = info["arguments"][argno + offset].get("callable_retained", False)
        if bool(st) != bool(retained):
            self.fail(
                message
                or "arg %d of %s; retained: %r, expected: %r"
                % (argno, method, st, retained)
            )

    def assertResultIsFunction(self, method, sel_type, message=None):
        info = method.__metadata__()

        try:
            i = info["retval"]
        except (KeyError, IndexError):
            self.fail(
                message or f"result of {method} has no metadata (or doesn't exist)"
            )

        else:
            typestr = i.get("type", b"@")

        if typestr != b"^?":
            self.fail(message or f"result of {method} is not of type function_pointer")

        st = i.get("callable")
        if st is None:
            self.fail(message or f"result of {method} is not of type function_pointer")

        try:
            iface = st["retval"]["type"]
            for a in st["arguments"]:
                iface += a["type"]
        except KeyError:
            self.fail(
                message
                or "result of %s is a function pointer with incomplete type information"
                % (method,)
            )

        if iface != sel_type:
            self.fail(
                message
                or "result of %s is not a function_pointer with type %r, but %r"
                % (method, sel_type, iface)
            )

    def assertArgIsBlock(self, method, argno, sel_type, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            typestr = info["arguments"][argno + offset]["type"]
        except (IndexError, KeyError):
            self.fail("arg %d of %s does not exist" % (argno, method))

        if typestr != b"@?":
            self.fail(
                message
                or "arg %d of %s is not of type block: %s" % (argno, method, typestr)
            )

        st = info["arguments"][argno + offset].get("callable")
        if st is None:
            self.fail(
                message
                or "arg %d of %s is not of type block: no callable" % (argno, method)
            )

        try:
            iface = st["retval"]["type"]
            if st["arguments"][0]["type"] != b"^v":
                self.fail(
                    message
                    or "arg %d of %s has an invalid block signature %r for argument 0"
                    % (argno, method, st["arguments"][0]["type"])
                )
            for a in st["arguments"][1:]:
                iface += a["type"]
        except KeyError:
            self.fail(
                message
                or "result of %s is a block pointer with incomplete type information"
                % (method,)
            )

        if iface != sel_type:
            self.fail(
                message
                or "arg %d of %s is not a block with type %r, but %r"
                % (argno, method, sel_type, iface)
            )

    def assertResultIsBlock(self, method, sel_type, message=None):
        info = method.__metadata__()

        try:
            typestr = info["retval"]["type"]
            if typestr != b"@?":
                self.fail(
                    message or f"result of {method} is not of type block: {typestr}"
                )
        except KeyError:
            self.fail(
                message or "result of {} is not of type block: {}".format(method, b"v")
            )

        st = info["retval"].get("callable")
        if st is None:
            self.fail(
                message
                or "result of %s is not of type block: no callable specified" % (method)
            )

        try:
            iface = st["retval"]["type"]
            if st["arguments"][0]["type"] != b"^v":
                self.fail(
                    message
                    or "result %s has an invalid block signature %r for argument 0"
                    % (method, st["arguments"][0]["type"])
                )
            for a in st["arguments"][1:]:
                iface += a["type"]
        except KeyError:
            self.fail(
                message
                or "result of %s is a block pointer with incomplete type information"
                % (method,)
            )

        if iface != sel_type:
            self.fail(
                message
                or "result of %s is not a block with type %r, but %r"
                % (method, sel_type, iface)
            )

    def assertResultIsSEL(self, method, sel_type, message=None):
        info = method.__metadata__()
        try:
            i = info["retval"]
        except (KeyError, IndexError):
            self.fail(
                message or f"result of {method} has no metadata (or doesn't exist)"
            )

        typestr = i.get("type", b"@")
        if typestr != objc._C_SEL:
            self.fail(message or f"result of {method} is not of type SEL")

        st = i.get("sel_of_type")
        if st != sel_type and _typemap(st) != _typemap(sel_type):
            self.fail(
                message
                or "result of %s doesn't have sel_type %r but %r"
                % (method, sel_type, st)
            )

    def assertArgIsSEL(self, method, argno, sel_type, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            i = info["arguments"][argno + offset]
        except (KeyError, IndexError):
            self.fail(
                message
                or "arg %d of %s has no metadata (or doesn't exist)" % (argno, method)
            )

        typestr = i.get("type", b"@")
        if typestr != objc._C_SEL:
            self.fail(message or "arg %d of %s is not of type SEL" % (argno, method))

        st = i.get("sel_of_type")
        if st != sel_type and _typemap(st) != _typemap(sel_type):
            self.fail(
                message
                or "arg %d of %s doesn't have sel_type %r but %r"
                % (argno, method, sel_type, st)
            )

    def assertResultIsBOOL(self, method, message=None):
        info = method.__metadata__()
        typestr = info["retval"]["type"]
        if typestr not in (objc._C_NSBOOL, objc._C_BOOL):
            self.fail(
                message or f"result of {method} is not of type BOOL, but {typestr!r}"
            )

    def assertArgIsBOOL(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        typestr = info["arguments"][argno + offset]["type"]
        if typestr not in (objc._C_NSBOOL, objc._C_BOOL):
            self.fail(
                message
                or "arg %d of %s is not of type BOOL, but %r" % (argno, method, typestr)
            )

    def assertArgIsFixedSize(self, method, argno, count, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            cnt = info["arguments"][argno + offset]["c_array_of_fixed_length"]
            if cnt != count:
                self.fail(
                    message
                    or "arg %d of %s is not a C-array of length %d"
                    % (argno, method, count)
                )
        except (KeyError, IndexError):
            self.fail(
                message
                or "arg %d of %s is not a C-array of length %d" % (argno, method, count)
            )

    def assertResultIsFixedSize(self, method, count, message=None):
        info = method.__metadata__()
        try:
            cnt = info["retval"]["c_array_of_fixed_length"]
            if cnt != count:
                self.fail(
                    message
                    or "result of %s is not a C-array of length %d" % (method, count)
                )
        except (KeyError, IndexError):
            self.fail(
                message
                or "result of %s is not a C-array of length %d" % (method, count)
            )

    def assertArgSizeInArg(self, method, argno, count, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        try:
            cnt = info["arguments"][argno + offset]["c_array_length_in_arg"]
        except (KeyError, IndexError):
            self.fail(
                message
                or "arg %d of %s is not a C-array of with length in arg %s"
                % (argno, method, count)
            )

        if isinstance(count, (list, tuple)):
            count2 = tuple(x + offset for x in count)
        else:
            count2 = count + offset
        if cnt != count2:
            self.fail(
                message
                or "arg %d of %s is not a C-array of with length in arg %s"
                % (argno, method, count)
            )

    def assertResultSizeInArg(self, method, count, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        cnt = info["retval"]["c_array_length_in_arg"]
        if cnt != count + offset:
            self.fail(
                message
                or "result %s is not a C-array of with length in arg %d"
                % (method, count)
            )

    def assertArgIsOut(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        typestr = info["arguments"][argno + offset]["type"]
        if not typestr.startswith(b"o^") and not typestr.startswith(b"o*"):
            self.fail(
                message or "arg %d of %s is not an 'out' argument" % (argno, method)
            )

    def assertArgIsInOut(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        typestr = info["arguments"][argno + offset]["type"]
        if not typestr.startswith(b"N^") and not typestr.startswith(b"N*"):
            self.fail(
                message or "arg %d of %s is not an 'inout' argument" % (argno, method)
            )

    def assertArgIsIn(self, method, argno, message=None):
        if isinstance(method, objc.selector):
            offset = 2
        else:
            offset = 0
        info = method.__metadata__()
        typestr = info["arguments"][argno + offset]["type"]
        if not typestr.startswith(b"n^") and not typestr.startswith(b"n*"):
            self.fail(
                message or "arg %d of %s is not an 'in' argument" % (argno, method)
            )

    def assertStartswith(self, value, test, message=None):
        if not value.startswith(test):
            self.fail(message or f"{value!r} does not start with {test!r}")

    def assertHasAttr(self, value, key, message=None):
        if not hasattr(value, key):
            self.fail(message or f"{key} is not an attribute of {value!r}")

    def assertNotHasAttr(self, value, key, message=None):
        if hasattr(value, key):
            self.fail(message or f"{key} is an attribute of {value!r}")

    def assertIsSubclass(self, value, types, message=None):
        if not issubclass(value, types):
            self.fail(message or f"{value} is not a subclass of {types!r}")

    def assertIsNotSubclass(self, value, types, message=None):
        if issubclass(value, types):
            self.fail(message or f"{value} is a subclass of {types!r}")

    def assertClassIsFinal(self, cls):
        if not isinstance(cls, objc.objc_class):
            self.fail(f"{cls} is not an Objective-C class")
        elif not cls.__objc_final__:
            self.fail(f"{cls} is not a final class")

    def assertProtocolExists(self, name):
        ok = True
        try:
            proto = objc.protocolNamed(name)

        except objc.ProtocolError:
            ok = False

        if not ok:
            self.fail(f"Protocol {name!r} does not exist")

        if not isinstance(proto, objc.formal_protocol):
            # Should never happen
            self.fail(f"Protocol {name!r} is not a protocol, but {type(proto)}")

    def assertPickleRoundTrips(self, value):
        try:
            buf = _pickle.dumps(value)
            clone = _pickle.loads(buf)
        except Exception:
            self.fail(f"{value} cannot be pickled")

        self.assertEqual(clone, value)
        self.assertIsInstance(clone, type(value))

    def _validateCallableMetadata(
        self, value, class_name=None, skip_simple_charptr_check=False
    ):
        if False and isinstance(value, objc.selector):
            # Check if the signature might contain types that are interesting
            # for this method. This avoids creating a metadata dict for 'simple'
            # methods.
            # XXX: Disabled this shortcut due to adding already_retained tests
            signature = value.signature
            if objc._C_PTR not in signature and objc._C_CHARPTR not in signature:
                return

        callable_meta = value.__metadata__()
        argcount = len(callable_meta["arguments"])

        for idx, meta in [("retval", callable_meta["retval"])] + list(
            enumerate(callable_meta["arguments"])
        ):
            if meta.get("already_retained", False) and meta.get(
                "already_cfretained", False
            ):
                self.fail(
                    f"{value}: {idx}: both already_retained and already_cfretained"
                )

            if meta["type"].endswith(objc._C_PTR + objc._C_CHR) or meta[
                "type"
            ].endswith(objc._C_CHARPTR):
                if meta.get("c_array_delimited_by_null", False):
                    self.fail(
                        f"{value}: {idx}: null-delimited 'char*', use _C_CHAR_AS_TEXT instead {class_name or ''}"
                    )
                if not skip_simple_charptr_check:
                    self.fail(f"{value}: {idx}: 'char*' {class_name or ''}")

            v = meta.get("c_array_size_in_arg", None)
            if isinstance(v, int):
                if not (0 <= v < argcount):
                    self.fail(
                        f"{value}: {idx}: c_array_size_in_arg out of range {v} {class_name or ''}"
                    )
            elif isinstance(v, tuple):
                b, e = v
                if not (0 <= b < argcount):
                    self.fail(
                        f"{value}: {idx}: c_array_size_in_arg out of range {b} {class_name or ''}"
                    )
                if not (0 <= e < argcount):
                    self.fail(
                        f"{value}: {idx}: c_array_size_in_arg out of range {e} {class_name or ''}"
                    )

            tp = meta["type"]
            if any(
                tp.startswith(pfx) for pfx in (objc._C_IN, objc._C_OUT, objc._C_INOUT)
            ):
                rest = tp[1:]
                if not rest.startswith(objc._C_PTR) and not rest.startswith(
                    objc._C_CHARPTR
                ):
                    self.fail(
                        f"{value}: {idx}: byref specifier on non-pointer: {tp} {class_name or ''}"
                    )

                rest = rest[1:]

                if rest.startswith(objc._C_STRUCT_B):
                    name, fields = objc.splitStructSignature(rest)
                    if not fields:
                        self.fail(
                            f"{value}: {idx}: byref to empty struct (handle/CFType?): {tp} {class_name or ''}"
                        )

            if not isinstance(value, objc.selector):
                # This gives too many false positives for selectors (sadly)
                if (
                    tp.startswith(objc._C_PTR)
                    and tp not in (b"^v", b"^?")
                    and tp != b"^{AudioBufferList=I[1{AudioBuffer=II^v}]}"
                    and tp != b"^{_CFArrayCallBacks=q^?^?^?^?}"
                ):
                    if tp[1:].startswith(objc._C_STRUCT_B):
                        name, fields = objc.splitStructSignature(tp[1:])
                        if not fields:
                            continue

                    if idx == "retval":
                        if any(
                            x in meta
                            for x in {
                                "deref_result_pointer",
                                "c_array_delimited_by_null",
                                "c_array_of_variable_length",
                                "c_array_length_in_arg",
                                "c_array_size_in_arg",
                            }
                        ):
                            continue
                    self.fail(
                        f"{value}: {idx}: pointer argument, but no by-ref annotation:{tp!r} {class_name or ''}"
                    )

    def assertCallableMetadataIsSane(
        self, module, *, exclude_cocoa=True, exclude_attrs=()
    ):
        # Do some sanity checking on module metadata for
        # callables.
        #
        # This test is *very* expensive, made slightly
        # better by excluding CoreFoundation/Foundation/AppKit
        # by default
        #
        # XXX: exclude_cocoa may exclude too much depending on
        #      import order.

        if hasattr(module, "__bundle__"):
            with self.subTest("validate framework identifier"):
                self.assertHasAttr(module, "__framework_identifier__")
                self.assertEqual(
                    module.__bundle__.bundleIdentifier(),
                    module.__framework_identifier__,
                )

        if exclude_cocoa:
            try:
                import Cocoa

                exclude_names = set(dir(Cocoa))

                # Don't exclude NSObject' because a number
                # of frameworks define categories on this class.
                exclude_names -= {"NSObject"}
            except ImportError:
                exclude_names = set()
        else:
            exclude_names = set()

        exclude_method_names = {
            "copyRenderedTextureForCGLContext_pixelFormat_bounds_isFlipped_",
            "newTaggedNSStringWithASCIIBytes__length__",
            "utf8ValueSafe",
            "utf8ValueSafe_",
            "isKeyExcludedFromWebScript_",
        }

        exclude_attrs = set(exclude_attrs)
        exclude_attrs.add("FBSMutableSceneClientSettings")
        exclude_attrs.add("FBSSceneClientSettings")
        exclude_attrs.add(("NSColor", "scn_C3DColorIgnoringColorSpace_success_"))
        exclude_attrs.add(
            ("AVKitPlatformColorClass", "scn_C3DColorIgnoringColorSpace_success_")
        )
        exclude_attrs.add(
            ("PDFKitPlatformColor", "scn_C3DColorIgnoringColorSpace_success_")
        )
        exclude_attrs.add(("SCNColor", "scn_C3DColorIgnoringColorSpace_success_"))
        exclude_attrs.add(("SKColor", "scn_C3DColorIgnoringColorSpace_success_"))
        exclude_attrs.add(
            (
                "NSObject",
                "copyRenderedTextureForCGLContext_pixelFormat_bounds_isFlipped_",
            )
        )
        exclude_attrs.add(
            (
                "NSObject",
                "newTaggedNSStringWithASCIIBytes__length__",
            )
        )
        exclude_attrs.add(
            (
                "NSObject",
                "utf8ValueSafe",
            )
        )
        exclude_attrs.add(
            (
                "NSObject",
                "utf8ValueSafe_",
            )
        )
        exclude_attrs.add(
            (
                "NSObject",
                "isKeyExcludedFromWebScript_",
            )
        )

        # Two (private) classes that end up being found in
        # test runs on macOS 10.12 and 10.13
        exclude_attrs.add("ABCDContact_ABCDContact_")
        exclude_attrs.add("ABCDGroup_ABCDGroup_")

        # Some bindings in CoreAudio with false positives
        exclude_attrs.add("AudioHardwareClaimAudioDeviceID")
        exclude_attrs.add("AudioHardwareClaimAudioStreamID")
        exclude_attrs.add("AudioHardwareDevicePropertyChanged")
        exclude_attrs.add("AudioHardwareDevicesCreated")
        exclude_attrs.add("AudioHardwareDevicesDied")
        exclude_attrs.add("AudioHardwareStreamPropertyChanged")
        exclude_attrs.add("AudioHardwareStreamsCreated")
        exclude_attrs.add("AudioHardwareStreamsDied")
        exclude_attrs.add("AudioObjectCreate")
        exclude_attrs.add("AudioObjectPropertiesChanged")
        exclude_attrs.add("AudioObjectsPublishedAndDied")

        # Calculate all (interesting) names in the module. This pokes into
        # the implementation details of objc.ObjCLazyModule to avoid loading
        # all attributes (which is expensive for larger bindings).
        if isinstance(module, objc.ObjCLazyModule) and False:
            module_names = []
            module_names.extend(
                cls.__name__
                for cls in objc.getClassList()
                if (not cls.__name__.startswith("_")) and ("." not in cls.__name__)
            )
            module_names.extend(module._ObjCLazyModule__funcmap or [])
            module_names.extend(module.__dict__.keys())
            todo = list(module._ObjCLazyModule__parents or [])
            while todo:
                parent = todo.pop()
                if isinstance(parent, objc.ObjCLazyModule):
                    module_names.extend(parent._ObjCLazyModule__funcmap or ())
                    todo.extend(parent._ObjCLazyModule__parents or ())
                    module_names.extend(parent.__dict__.keys())
                else:
                    module_names.extend(dir(module))

            # The module_names list might contain duplicates
            module_names = sorted(set(module_names))
        else:
            module_names = sorted(set(dir(module)))

        for _idx, nm in enumerate(module_names):
            # print(f"{_idx}/{len(module_names)} {nm}")
            if nm in exclude_names:
                continue
            if nm in exclude_attrs:
                continue

            try:
                value = getattr(module, nm)
            except AttributeError:
                continue
            if isinstance(value, objc.objc_class):
                if value.__name__ == "Object":
                    # Root class, does not conform to the NSObject
                    # protocol and useless to test.
                    continue
                for attr_name, attr in value.pyobjc_instanceMethods.__dict__.items():
                    if attr_name in exclude_method_names:
                        continue
                    if (nm, attr_name) in exclude_attrs:
                        continue
                    if attr_name.startswith("_"):
                        # Skip private names
                        continue

                    with self.subTest(classname=nm, instance_method=attr_name):
                        if isinstance(attr, objc.selector):  # pragma: no branch
                            self._validateCallableMetadata(
                                attr, nm, skip_simple_charptr_check=not exclude_cocoa
                            )

                for attr_name, attr in value.pyobjc_classMethods.__dict__.items():
                    if attr_name in exclude_method_names:
                        continue
                    if (nm, attr_name) in exclude_attrs:
                        continue
                    if attr_name.startswith("_"):
                        # Skip private names
                        continue

                    with self.subTest(classname=nm, instance_method=attr_name):
                        attr = getattr(value.pyobjc_classMethods, attr_name, None)
                        if isinstance(attr, objc.selector):  # pragma: no branch
                            self._validateCallableMetadata(
                                attr, nm, skip_simple_charptr_check=not exclude_cocoa
                            )
            elif isinstance(value, objc.function):
                with self.subTest(function=nm):
                    self._validateCallableMetadata(value)

            else:
                continue

    def __init__(self, methodName="runTest"):
        super().__init__(methodName)

        testMethod = getattr(self, methodName)

        if getattr(testMethod, "_no_autorelease_pool", False):
            self._skip_usepool = True
        else:
            self._skip_usepool = False

    def run(self, *args, **kwds):
        """
        Run the test, same as unittest.TestCase.run, but every test is
        run with a fresh autorelease pool.
        """
        try:
            cls = objc.lookUpClass("NSApplication")
        except objc.error:
            pass
        else:
            cls.sharedApplication()

        if _usepool and not self._skip_usepool:
            p = _poolclass.alloc().init()
        else:
            p = 1

        try:
            _unittest.TestCase.run(self, *args, **kwds)
        finally:
            _gc.collect()
            del p
            _gc.collect()


main = _unittest.main
expectedFailure = _unittest.expectedFailure
skipUnless = _unittest.skipUnless
SkipTest = _unittest.SkipTest


def expectedFailureIf(condition):
    if condition:
        return expectedFailure
    else:
        return lambda func: func


def no_autorelease_pool(func):
    func._no_autorelease_pool = True
    return func
