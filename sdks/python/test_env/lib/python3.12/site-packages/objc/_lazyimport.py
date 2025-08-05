"""
Helper module that will enable lazy imports of Cocoa wrapper items.

This improves startup times and memory usage, at the cost
of not being able to use 'from Cocoa import *'
"""

__all__ = ("ObjCLazyModule", "createFrameworkDirAndGetattr")

import re
import struct
import sys
import warnings

import objc
import types
from collections import ChainMap
from objc import getClassList, loadBundle, lookUpClass, nosuchclass_error

ModuleType = types.ModuleType

_name_re = re.compile("^[A-Za-z_][A-Za-z_0-9]*$")

_DEFAULT_ALIASES = {
    "ULONG_MAX": (sys.maxsize * 2) + 1,
    "LONG_MAX": sys.maxsize,
    "LONG_MIN": -sys.maxsize - 1,
    "DBL_MAX": sys.float_info.max,
    "DBL_MIN": sys.float_info.min,
    "DBL_EPSILON": sys.float_info.epsilon,
    "FLT_MAX": objc._FLT_MAX,
    "FLT_MIN": objc._FLT_MIN,
    "objc.NULL": objc.NULL,
    "UINT32_MAX": 0xFFFFFFFF,
}


def _deprecation_level(value):
    if isinstance(value, int):
        return value
    major, _, minor = value.partition(".")
    return int(major) * 100 + int(minor)


def _check_deprecated(name, deprecation_version):
    if (
        objc.options.deprecation_warnings != "0.0"
        and _deprecation_level(objc.options.deprecation_warnings) >= deprecation_version
    ):
        warnings.warn(
            "%r is deprecated in macOS %d.%d"
            % (name, deprecation_version / 100, deprecation_version % 100),
            objc.ApiDeprecationWarning,
            stacklevel=2,
        )


def _prs_enum(val):
    if val.startswith("'"):
        (val,) = struct.unpack(">l", val[1:-1].encode("latin1"))

    elif "." in val or "e" in val:
        val = float(val)

    else:
        val = int(val)

    return val


def _loadBundle(frameworkName, frameworkIdentifier, frameworkPath):
    if frameworkIdentifier is None:
        bundle = loadBundle(
            frameworkName, {}, bundle_path=frameworkPath, scan_classes=False
        )

    else:
        try:
            bundle = loadBundle(
                frameworkName,
                {},
                bundle_identifier=frameworkIdentifier,
                scan_classes=False,
            )

        except ImportError:
            bundle = loadBundle(
                frameworkName, {}, bundle_path=frameworkPath, scan_classes=False
            )

    return bundle


class _GetAttrMap:
    __slots__ = ("_getattr",)

    def __init__(self, getattr_func):
        self._getattr = getattr_func

    def __getitem__(self, key):
        if key == "CFSTR":
            return lambda v: v.decode()
        try:
            return self._getattr(key)
        except AttributeError:
            raise KeyError(key)


def createFrameworkDirAndGetattr(
    *,
    name,
    frameworkIdentifier,
    frameworkPath,
    globals_dict,
    metadict,
    inline_list,
    parents,
):
    """
    Load the specified framework and return ``__dir__`` and ``__getattr__`` for the
    framework bindings.

    The result should be assigned to module constants, e.g. in SomeFramework.py use:

       __dir__, __getattr__ = objc.createFrameworkDirAndGetattr("SomeFramework", "...", "...", globals(), ...)
    """

    # XXX: Implementation can be cleaned up, I've basically moved the old implementation
    #      from ObjCLazyModule into this function with minor touch ups.

    if frameworkIdentifier is not None or frameworkPath is not None:
        bundle = globals_dict["__bundle__"] = _loadBundle(
            name, frameworkIdentifier, frameworkPath
        )
    else:
        bundle = None

    if metadict is None:
        metadict = {}

    globals_dict["__framework_identifier__"] = frameworkIdentifier
    globals_dict.update(metadict.get("misc", {}))

    varmap = metadict.get("constants")
    varmap_deprecated = metadict.get("deprecated_constants", {})
    varmap_dct = metadict.get("constants_dict", {})
    enummap = metadict.get("enums")
    enum_deprecated = metadict.get("deprecated_enums", {})
    funcmap = metadict.get("functions")
    aliases = metadict.get("aliases")
    aliases_deprecated = metadict.get("deprecated_aliases", {})

    # XXX: informal protocols are not exposed, but added here
    # for completeness sake.
    # informal_protocols = metadict.get("protocols")

    expressions = metadict.get("expressions")

    def __dir__():
        if "__all__" in globals_dict:
            return globals_dict["__all__"]

        globals_dict["__all__"] = calc_all()
        return globals_dict["__all__"]

    def __getattr__(name):
        if name == "__all__":
            # Load everything immediately
            value = calc_all()
            globals_dict[name] = value
            return value

        # First try parent module, as if we had done
        # 'from parents import *' (andh hence don't
        # look for private names in parent modules)
        if not name.startswith("_"):
            for p in parents:
                try:
                    value = getattr(p, name)
                    globals_dict[name] = value
                    return value
                except AttributeError:
                    pass

        if not _name_re.match(name):
            # Name is not a valid identifier and cannot
            # match.
            raise AttributeError(name)

        # Check if the name is a constant from
        # the metadata files
        try:
            value = get_constant(name)
        except AttributeError:
            pass

        else:
            globals_dict[name] = value
            return value

        # Then check if the name is class
        try:
            value = lookUpClass(name)
        except nosuchclass_error:
            pass

        else:
            globals_dict[name] = value
            return value

        # Finally give up and raise AttributeError
        raise AttributeError(name)

    def calc_all():
        # Ensure that all dynamic entries get loaded
        #
        # The code tries to resolve through 'expressions_mapping'
        # to avoid code duplication, and to get some edge cases correct
        nonlocal varmap, enummap, inline_list, expressions, aliases

        if varmap_dct:
            for nm in list(varmap_dct):
                try:
                    expressions_mapping[nm]
                except KeyError:
                    pass

            varmap_dct.clear()

        if varmap:
            for nm, _tp in re.findall(r"\$([A-Z0-9a-z_]*)(@[^$]*)?(?=\$)", varmap):
                # An empty name can happen if the 'constants' definition
                # is effectively happened (e.g. "$$").
                if not nm:
                    continue

                try:
                    expressions_mapping[nm]
                except KeyError:
                    continue

            varmap = ""

        if enummap:
            for nm, _val in re.findall(r"\$([A-Z0-9a-z_]*)@([^$]*)(?=\$)", enummap):
                try:
                    expressions_mapping[nm]
                except KeyError:
                    pass

            enummap = ""

        if funcmap:
            for nm in list(funcmap):
                try:
                    expressions_mapping[nm]
                except KeyError:
                    pass

            funcmap.clear()

        inline_list = None

        if expressions:
            for nm in list(expressions):
                try:
                    expressions_mapping[nm]
                except KeyError:
                    pass
            expressions = []

        if aliases:
            for nm in list(aliases):
                try:
                    expressions_mapping[nm]
                except KeyError:
                    pass
            aliases = []

        all_names = set()

        # Add all names that are already globals_dict__
        all_names.update(globals_dict)

        # Merge __all__of parents ('from parent import *')
        for p in parents:
            try:
                all_names.update(p.__all__)
            except AttributeError:
                all_names.update(dir(p))

        # Add all class names, ignoring names that aren't valid identifiers
        all_names.update(
            cls.__name__ for cls in getClassList(True) if cls.__name__.isidentifier()
        )

        return sorted({v for v in all_names if not v.startswith("_")})

    def get_constant(name):
        if varmap_dct:
            if name in varmap_dct:
                tp = varmap_dct[name]
                if tp.startswith("=="):
                    tp = tp[2:]
                    magic = 2
                elif tp.startswith("="):
                    tp = tp[1:]
                    magic = 1
                else:
                    magic = 0
                result = objc._loadConstant(name, tp, magic)
                varmap_dct.pop(name)
                if name in varmap_deprecated:
                    _check_deprecated(name, varmap_deprecated[name])

                return result

        if varmap:
            m = re.search(rf"\${name}(@[^$]*)?\$", varmap)
            if m is not None:
                tp = m.group(1)
                if not tp:
                    tp = "@"
                else:
                    tp = tp[1:]

                d = {}
                if tp.startswith("=="):
                    magic = 2
                    tp = tp[2:]
                elif tp.startswith("="):
                    tp = tp[1:]
                    magic = 1
                else:
                    magic = 0

                result = objc._loadConstant(name, tp, magic)

                if name in varmap_deprecated:
                    _check_deprecated(name, varmap_deprecated[name])

                return result

        if enummap:
            m = re.search(rf"\${name}@([^$]*)\$", enummap)
            if m is not None:
                result = _prs_enum(m.group(1))
                if name in enum_deprecated:
                    _check_deprecated(name, enum_deprecated[name])
                return result

        if funcmap:
            if name in funcmap:
                info = funcmap[name]

                func_list = [(name,) + info]

                d = {}
                objc.loadBundleFunctions(bundle, d, func_list)
                if name in d:
                    funcmap.pop(name)
                    return d[name]

                if inline_list is not None:
                    objc.loadFunctionList(
                        inline_list, d, func_list, skip_undefined=True
                    )
                    if name in d:
                        return d[name]

        if expressions:
            if name in expressions:
                info = expressions[name]
                try:
                    result = eval(info, {}, expressions_mapping)
                    expressions.pop(name)
                    return result
                except:  # noqa: E722, B001. Ignore all errors in evaluation the expression.
                    pass

        if aliases:
            if name in aliases:
                alias = aliases[name]
                aliases.pop(name)

                if alias in _DEFAULT_ALIASES:
                    result = _DEFAULT_ALIASES[alias]
                else:
                    try:
                        result = expressions_mapping[alias]
                    except KeyError:
                        raise AttributeError(name)

                if name in aliases_deprecated:
                    _check_deprecated(name, aliases_deprecated[name])
                return result

        raise AttributeError(name)

    def load_cftypes(cftypes):
        if not cftypes:
            return

        for name, typestr, gettypeid_func, tollfree in cftypes:
            if tollfree:
                for nm in tollfree.split(","):  # pragma: no branch
                    try:
                        objc.lookUpClass(nm)
                    except objc.error:
                        pass
                    else:
                        tollfree = nm
                        break
                try:
                    v = objc.registerCFSignature(name, typestr, None, tollfree)
                    globals_dict[name] = v
                    continue
                except objc.nosuchclass_error:
                    pass

            if gettypeid_func is None:
                func = None

            else:
                try:
                    func = expressions_mapping[gettypeid_func]
                except KeyError:
                    func = None

            if func is None:
                # GetTypeID function not found, this is either
                # a CFType that isn't present on the current
                # platform, or a CFType without a public GetTypeID
                # function. Proxy using the generic CFType
                if tollfree is None:
                    v = objc.registerCFSignature(name, typestr, None, "NSCFType")
                    globals_dict[name] = v

                continue

            v = objc.registerCFSignature(name, typestr, func())
            globals_dict[name] = v

    expressions_mapping = ChainMap(globals_dict, _GetAttrMap(__getattr__))
    load_cftypes(metadict.get("cftypes"))

    return __dir__, __getattr__


class ObjCLazyModule(ModuleType):
    """
    A module type that loads PyObjC metadata lazily, that is constants, global
    variables and functions are created from the metadata as needed. This
    reduces the resource usage of PyObjC (both in time and memory), as most
    symbols exported by frameworks are never used in programs.

    The loading code assumes that the metadata dictionary is valid, and invalid
    metadata may cause exceptions other than AttributeError when accessing module
    attributes.
    """

    def __init__(
        self,
        name,
        frameworkIdentifier,
        frameworkPath,
        metadict=None,
        inline_list=None,
        initialdict=None,
        parents=(),
    ):
        # warnings.warn(
        #    "'ObjCLazyModule' is deprecated, use 'createFrameworkDirAndGetattr' instead",
        #    DeprecationWarning,
        #    stacklevel=2,
        # )
        super().__init__(name)
        self.__dir__, self.__getattr__ = createFrameworkDirAndGetattr(
            name=name,
            frameworkIdentifier=frameworkIdentifier,
            frameworkPath=frameworkPath,
            globals_dict=self.__dict__,
            inline_list=inline_list,
            parents=parents,
            metadict=metadict,
        )

        pfx = name + "."
        for nm in list(sys.modules.keys()):
            # See issue #95: there can be objects that aren't strings in
            # sys.modules.
            if hasattr(nm, "startswith") and nm.startswith(pfx):
                rest = nm[len(pfx) :]  # noqa: E203
                if "." in rest:
                    continue
                if sys.modules[nm] is not None:
                    self.__dict__[rest] = sys.modules[nm]

        if initialdict:
            self.__dict__.update(initialdict)
