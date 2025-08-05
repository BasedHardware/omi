"""
Backward compatibility with bridgesupport files

This functionality is deprecated and will be removed in PyObjC 10.
"""

__all__ = ("initFrameworkWrapper", "parseBridgeSupport")

import os
import re
import sys
import warnings
import xml.etree.ElementTree as ET
from importlib import resources

import objc

ctypes = None

for method in (
    b"alloc",
    b"copy",
    b"copyWithZone:",
    b"mutableCopy",
    b"mutableCopyWithZone:",
):
    objc.registerMetaDataForSelector(
        b"NSObject", method, {"retval": {"already_retained": True}}
    )


#
# The rest of this file contains support for bridgesupport
# XML files.

# NOTE: This search path only contains system locations to
# avoid accidentally reiying on system-specific functionality.
BRIDGESUPPORT_DIRECTORIES = ["/System/Library/BridgeSupport"]

_SENTINEL = object()
_DEFAULT_SUGGESTION = "don't use this method"
_BOOLEAN_ATTRIBUTES = [
    "already_retained",
    "already_cfretained",
    "c_array_length_in_result",
    "c_array_delimited_by_null",
    "c_array_of_variable_length",
    "printf_format",
    "free_result",
]


def _get_ctypes():
    global ctypes

    if ctypes is None:
        import ctypes


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    return value.encode("ascii")


class _BridgeSupportParser:
    """
    Parser for the bridge support file format.

    Instances of this class will not update the bridge state,
    this makes it easier to test the class.
    """

    TAG_MAP = {}

    def __init__(self, xmldata, frameworkName):
        self.frameworkName = frameworkName

        self.cftypes = []
        self.constants = []
        self.func_aliases = []
        self.functions = []
        self.informal_protocols = []
        self.meta = {}
        self.opaque = []
        self.structs = []
        self.values = {}

        self.process_data(xmldata)

    def process_data(self, xmldata):
        root = ET.fromstring(xmldata.strip())

        if root.tag != "signatures":
            raise objc.error("invalid root node in bridgesupport file")

        for node in root:
            method = getattr(self, f"do_{node.tag}", None)
            if method is None:
                continue

            method(node)

    def typestr2typestr(self, typestr):
        typestr = _as_bytes(typestr)

        # As of macOS 10.13 metadata files may contain
        # typestring that end with property specific data;
        # first remove that junk.
        if b"," in typestr:  # pragma: no branch
            typestr = typestr.split(b",", 1)[0]  # pragma: no cover

        result = []
        for item in objc.splitSignature(typestr):
            if item == objc._C_BOOL:
                result.append(objc._C_NSBOOL)

            elif item == objc._C_NSBOOL:
                result.append(objc._C_BOOL)

            elif item.startswith(objc._C_STRUCT_B) or item.startswith(objc._C_UNION_B):
                # unions and structs have the same structure
                start, stop = item[:1], item[-1:]

                name, fields = objc.splitStructSignature(
                    objc._C_STRUCT_B + _as_bytes(item[1:-1]) + objc._C_STRUCT_E
                )
                result.append(start)
                if name is not None:  # pragma: no branch
                    result.append(_as_bytes(name))
                    result.append(b"=")
                for nm, tp in fields:
                    if nm is not None:  # pragma: no branch
                        result.append(b'"')  # pragma: no cover
                        result.append(_as_bytes(nm))  # pragma: no cover
                        result.append(b'"')  # pragma: no cover

                    result.append(self.typestr2typestr(tp))
                result.append(stop)

            elif item.startswith(objc._C_ARY_B):  # pragma: no branch
                m = re.match(rb"^.(\d*)(.*).$", item)  # pragma: no cover
                result.append(objc._C_ARY_B)  # pragma: no cover
                result.append(m.group(1))  # pragma: no cover
                result.append(self.typestr2typestr(m.group(2)))  # pragma: no cover
                result.append(objc._C_ARY_E)  # pragma: no cover

            else:
                result.append(item)

        return b"".join(result)

    if sys.maxsize > 2**32:

        def attribute_string(self, node, name, name64):
            if name64 is not None:
                value = node.get(name64)
                if value is not None:
                    return value

            return node.get(name)

    else:

        def attribute_string(self, node, name, name64):
            return node.get(name)

    def attribute_bool(self, node, name, name64, dflt):
        value = self.attribute_string(node, name, name64)
        if value is None:
            return dflt

        if value == "true":
            return True

        return False

    def import_name(self, name):
        module, field = name.rsplit(".", 1)
        m = __import__(module)
        try:
            for nm in module.split(".")[1:]:
                m = getattr(m, nm)

            return getattr(m, field)

        except AttributeError:
            raise ImportError(name)

    def xml_to_arg(self, node, is_method, is_arg):
        argIdx = None
        result = {}

        if is_arg and is_method:
            argIdx = self.attribute_string(node, "index", None)
            if argIdx is None:
                return None, None
            argIdx = int(argIdx)

        s = self.attribute_string(node, "type", "type64")
        if s:
            s = self.typestr2typestr(s)
            result["type"] = s

        s = self.attribute_string(node, "type_modifier", None)
        if s:
            result["type_modifier"] = _as_bytes(s)

        s = self.attribute_string(node, "sel_of_type", "sel_of_type64")
        if s:
            result["sel_of_type"] = self.typestr2typestr(s)

        s = self.attribute_string(node, "c_array_of_fixed_length", None)
        if s:
            result["c_array_of_fixed_length"] = int(s)

        for attr in _BOOLEAN_ATTRIBUTES:
            if attr == "c_array_length_in_result" and not is_arg:
                continue
            s = self.attribute_bool(node, attr, None, False)
            if s:
                result[attr] = True

        s = self.attribute_bool(node, "null_accepted", None, True)
        if not s:
            result["null_accepted"] = False

        s = self.attribute_string(node, "c_array_length_in_arg", None)
        if s:
            if "," in s:
                start, stop = map(int, s.split(","))
                if is_method:
                    start += 2
                    stop += 2

                result["c_array_length_in_arg"] = (start, stop)

            else:
                s = int(s)
                if is_method:
                    s += 2

                result["c_array_length_in_arg"] = s

        if self.attribute_bool(
            node, "function_pointer", None, False
        ) or self.attribute_bool(node, "block", None, False):
            v = self.attribute_bool(node, "function_pointer_retained", None, True)
            result["callable_retained"] = v

            meta = result["callable"] = {}
            arguments = meta["arguments"] = {}
            idx = 0

            if self.attribute_bool(node, "block", None, False):
                # Blocks have an implicit first argument
                arguments[idx] = {"type": b"^v"}
                idx += 1

            for al in node:
                if al.tag == "arg":
                    _, d = self.xml_to_arg(al, False, False)
                    arguments[idx] = d
                    idx += 1

                elif al.tag == "retval":
                    _, d = self.xml_to_arg(al, False, False)
                    meta["retval"] = d

        return argIdx, result

    def do_cftype(self, node):
        _get_ctypes()

        name = self.attribute_string(node, "name", None)
        typestr = self.attribute_string(node, "type", "type64")
        funcname = self.attribute_string(node, "gettypeid_func", None)
        tollfree = self.attribute_string(node, "tollfree", None)

        if not name or not typestr:
            return

        typestr = self.typestr2typestr(typestr)

        if tollfree:
            self.cftypes.append((name, typestr, None, tollfree))

        else:
            if funcname is None:
                funcname = name[:-3] + "GetTypeID"

            try:
                dll = ctypes.CDLL(None)
                gettypeid = getattr(dll, funcname)
                gettypeid.restype = ctypes.c_long
            except AttributeError:
                self.cftypes.append((name, typestr, None, "NSCFType"))
                return

            self.cftypes.append((name, typestr, gettypeid()))

    def do_constant(self, node):
        name = self.attribute_string(node, "name", None)
        typestr = self.attribute_string(node, "type", "type64")

        if name is None or not typestr:
            return

        typestr = self.typestr2typestr(typestr)

        if typestr.startswith(objc._C_STRUCT_B):
            # Look for structs with embedded function pointers
            # and ignore those

            def has_embedded_function(typestr):
                nm, fields = objc.splitStructSignature(_as_bytes(typestr))
                for _nm, tp in fields:  # pragma: no branch
                    if tp == b"?":
                        return True
                    elif tp == b"^?":  # pragma: no branch
                        return True  # pragma: no cover
                    elif tp.startswith(objc._C_STRUCT_B):
                        return has_embedded_function(tp)

                return False  # pragma: no cover

            if has_embedded_function(typestr):  # pragma: no branch
                return

        magic = self.attribute_bool(node, "magic_cookie", None, False)
        self.constants.append((name, typestr, magic))

    def do_class(self, node):
        class_name = self.attribute_string(node, "name", None)
        if not class_name:
            return

        for method in node:
            if method.tag != "method":
                continue

            sel_name = self.attribute_string(method, "selector", None)
            if sel_name is None:
                continue

            sel_name = _as_bytes(sel_name)
            variadic = self.attribute_bool(method, "variadic", None, False)
            c_array = self.attribute_bool(
                method, "c_array_delimited_by_null", None, False
            )
            c_length = self.attribute_string(method, "c_array_length_in_arg", None)
            ignore = self.attribute_bool(method, "ignore", None, False)

            is_class = self.attribute_bool(method, "classmethod", None, _SENTINEL)
            if is_class is _SENTINEL:
                # Manpage says 'class_method', older PyObjC used 'classmethod'
                is_class = self.attribute_bool(method, "class_method", None, False)

            metadata = {}
            if ignore:
                suggestion = self.attribute_string(method, "suggestion", None)
                if not suggestion:
                    suggestion = _DEFAULT_SUGGESTION

                metadata["suggestion"] = suggestion

                # Force minimal metadata for ignored methods
                self.meta[(_as_bytes(class_name), _as_bytes(sel_name), is_class)] = (
                    metadata
                )
                continue

            if variadic:
                metadata["variadic"] = True
                if c_array:
                    metadata["c_array_delimited_by_null"] = c_array

                if c_length:
                    metadata["c_array_length_in_arg"] = int(c_length) + 2

            arguments = metadata["arguments"] = {}

            for al in method:
                if al.tag == "arg":
                    arg_idx, meta = self.xml_to_arg(al, True, True)
                    if arg_idx is not None and meta:
                        arguments[arg_idx + 2] = meta

                elif al.tag == "retval":
                    _, meta = self.xml_to_arg(al, True, False)
                    if meta:
                        metadata["retval"] = meta

            if not arguments:
                # No argument metadata after all.
                del metadata["arguments"]

            if metadata:
                self.meta[(_as_bytes(class_name), _as_bytes(sel_name), is_class)] = (
                    metadata
                )

    def do_enum(self, node):
        name = self.attribute_string(node, "name", None)
        value = self.attribute_string(node, "value", "value64")

        if value is None:
            if sys.byteorder == "little":
                value = self.attribute_string(node, "le_value", None)

            else:
                value = self.attribute_string(node, "be_value", None)

        if not name or not value:
            return

        if value.endswith("l") or value.endswith("L"):
            value = value[:-1]

        if value.lower() in ("+inf", "-inf", "nan"):
            value = float(value)

        elif "." in value:
            if value.endswith("f") or value.endswith("F"):
                value = value[:-1]
            if value.startswith("0x") or value.startswith("0X"):
                value = float.fromhex(value)

            else:
                value = float(value)

        elif "inf" in value:
            value = float(value)

        else:
            value = int(value, 10)

        self.values[name] = value

    def do_function(self, node):
        name = self.attribute_string(node, "name", None)
        if not name:
            return

        if self.attribute_bool(node, "ignore", None, False):
            return

        meta = {}
        siglist = [b"v"]
        arguments = meta["arguments"] = {}

        variadic = self.attribute_bool(node, "variadic", None, False)
        if variadic:
            meta["variadic"] = True
            v = self.attribute_bool(node, "c_array_delimited_by_null", None, False)
            if v:
                meta["c_array_delimited_by_null"] = True

            v = self.attribute_string(node, "c_array_length_in_arg", None)
            if v:
                meta["c_array_length_in_arg"] = int(v)

        for al in node:
            if al.tag == "arg":
                _, d = self.xml_to_arg(al, False, True)
                if "type" not in d:
                    # Ignore functions without type info
                    return
                siglist.append(d["type"])

                arguments[len(siglist) - 2] = d

            elif al.tag == "retval":
                _, d = self.xml_to_arg(al, False, False)
                if "type" not in d:
                    # Ignore functions without type info
                    return
                siglist[0] = d["type"]
                meta["retval"] = d

        if not meta["arguments"]:
            del meta["arguments"]

        self.functions.append((name, b"".join(siglist), "", meta))

    def do_function_pointer(self, node):
        name = self.attribute_string(node, "name", None)
        original = self.attribute_string(node, "original", None)
        if not name or not original:
            return

        self.func_aliases.append((name, original))

    def do_informal_protocol(self, node):
        name = self.attribute_string(node, "name", None)
        if not name:
            return

        method_list = []
        for method in node:
            sel_name = self.attribute_string(method, "selector", None)
            typestr = self.attribute_string(method, "type", "type64")
            is_class = self.attribute_bool(method, "classmethod", None, _SENTINEL)
            if is_class is _SENTINEL:
                # Manpage says 'class_method', older PyObjC used 'classmethod'
                is_class = self.attribute_bool(method, "class_method", None, False)

            if not sel_name or not typestr:
                continue

            typestr = self.typestr2typestr(typestr)
            sel = objc.selector(
                None,
                selector=_as_bytes(sel_name),
                signature=_as_bytes(typestr),
                isClassMethod=is_class,
            )
            method_list.append(sel)

        if method_list:
            self.informal_protocols.append((name, method_list))

    def do_null_const(self, node):
        name = self.attribute_string(node, "name", None)
        if not name:
            return

        self.values[name] = None

    def do_opaque(self, node):
        name = self.attribute_string(node, "name", None)
        typestr = self.attribute_string(node, "type", "type64")

        if name is None or not typestr:
            return

        typestr = self.typestr2typestr(typestr)

        self.opaque.append((name, typestr))

    def do_struct(self, node):
        name = self.attribute_string(node, "name", None)
        typestr = self.attribute_string(node, "type", "type64")
        alias = self.attribute_string(node, "alias", None)

        if not name or not typestr:
            return

        # Apple's bridgesupport files contain nice encoding like this:
        # {tag="field"a"NSImage"}, that is not only are field names encoded
        # but also class names. This is obviously completely undocumented,
        # and not backward compatible (and it is not easily possible to detect
        # if class names are present.
        typestr = re.sub(r'@"[^"]*"', "@", typestr)

        typestr = self.typestr2typestr(typestr)

        if alias:
            try:
                value = self.import_name(alias)
            except ImportError:
                # Fall through to regular handling
                pass

            else:
                self.structs.append((name, typestr, value))
                return

        self.structs.append((name, typestr, None))

    def do_string_constant(self, node):
        name = self.attribute_string(node, "name", None)
        value = self.attribute_string(node, "value", "value64")
        nsstring = self.attribute_bool(node, "nsstring", None, False)

        if not name or not value:
            return

        if not nsstring:
            try:
                value = value.encode("latin1")
            except UnicodeError as e:
                warnings.warn(
                    f"Error parsing BridgeSupport data for constant {name}: {e}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return

        self.values[name] = value


_libraries = []


def parseBridgeSupport(
    xmldata, globals, frameworkName, dylib_path=None, inlineTab=None  # noqa: A002
):
    warnings.warn(
        "This function will be removed in PyObjC 10, switch to the modern metadata system",
        DeprecationWarning,
        stacklevel=2,
    )

    if dylib_path:
        _get_ctypes()
        lib = ctypes.cdll.LoadLibrary(dylib_path)
        _libraries.append(lib)

    objc._updatingMetadata(True)
    try:
        prs = _BridgeSupportParser(xmldata, frameworkName)

        globals.update(prs.values)
        for entry in prs.cftypes:
            tp = objc.registerCFSignature(*entry)

            globals[entry[0]] = tp

        for name, typestr in prs.opaque:
            globals[name] = objc.createOpaquePointerType(name, typestr)

        for name, typestr, alias in prs.structs:
            if alias is not None:
                globals[name] = alias
                objc.createStructAlias(name, typestr, alias)
            else:
                globals[name] = value = objc.createStructType(name, typestr, None)

        for name, typestr, magic in prs.constants:
            try:
                value = objc._loadConstant(name, typestr.decode("ascii"), magic)
            except AttributeError:
                continue

            globals[name] = value

        for class_name, sel_name, is_class in prs.meta:
            objc.registerMetaDataForSelector(
                class_name, sel_name, prs.meta[(class_name, sel_name, is_class)]
            )

        if prs.functions:
            objc.loadBundleFunctions(None, globals, prs.functions)

            if inlineTab is not None:
                objc.loadFunctionList(inlineTab, globals, prs.functions)

        for name, orig in prs.func_aliases:
            try:
                globals[name] = globals[orig]
            except KeyError:
                pass

    finally:
        objc._updatingMetadata(False)


def _parseBridgeSupport(data, globals, frameworkName, *args, **kwds):  # noqa: A002
    try:
        objc.parseBridgeSupport(data, globals, frameworkName, *args, **kwds)
    except objc.internal_error as e:
        import warnings

        warnings.warn(
            f"Error parsing BridgeSupport data for {frameworkName}: {e}",
            RuntimeWarning,
            stacklevel=2,
        )


if sys.version_info[:2] >= (3, 9):

    def resource_exists(package, resource):
        try:
            return resources.files(package).joinpath(resource).is_file()

        except ImportError:
            return False

else:

    def resource_exists(package, resource):
        try:
            return resources.is_resource(package, resource)

        except ImportError:
            return False


if sys.version_info[:2] >= (3, 9):

    def resource_string(package, resource):
        return resources.files(package).joinpath(resource).read_text()

else:

    def resource_string(package, resource):
        return resources.read_text(package, resource)


def initFrameworkWrapper(
    frameworkName,
    frameworkPath,
    frameworkIdentifier,
    globals,  # noqa: A002
    inlineTab=None,
    scan_classes=None,
    frameworkResourceName=None,
):
    """
    Load the named framework, using the identifier if that has result otherwise
    using the path. Also loads the information in the bridgesupport file (
    either one embedded in the framework or one in a BrigeSupport library
    directory).
    """
    warnings.warn(
        "This function will be removed in PyObjC 9, switch to the modern metadata system",
        DeprecationWarning,
        stacklevel=2,
    )
    if frameworkResourceName is None:
        frameworkResourceName = frameworkName

    if frameworkIdentifier is None:
        if scan_classes is None:
            bundle = objc.loadBundle(frameworkName, globals, bundle_path=frameworkPath)
        else:
            bundle = objc.loadBundle(
                frameworkName,
                globals,
                bundle_path=frameworkPath,
                scan_classes=scan_classes,
            )

    else:
        try:
            if scan_classes is None:
                bundle = objc.loadBundle(
                    frameworkName, globals, bundle_identifier=frameworkIdentifier
                )

            else:
                bundle = objc.loadBundle(
                    frameworkName,
                    globals,
                    bundle_identifier=frameworkIdentifier,
                    scan_classes=scan_classes,
                )

        except ImportError:
            if scan_classes is None:
                bundle = objc.loadBundle(
                    frameworkName, globals, bundle_path=frameworkPath
                )
            else:
                bundle = objc.loadBundle(
                    frameworkName,
                    globals,
                    bundle_path=frameworkPath,
                    scan_classes=scan_classes,
                )

    # Make the objc module available, because it contains a lot of useful
    # functionality.
    globals["objc"] = objc

    # Explicitly push objc.super into the globals dict, that way super
    # calls will behave as expected in all cases.
    globals["super"] = objc.super

    # Look for metadata in the Python wrapper and prefer that over the
    # data in the framework or in system locations.
    # Needed because the system bridgesupport files are buggy.
    if resource_exists(frameworkResourceName, "PyObjC.bridgesupport"):
        data = resource_string(frameworkResourceName, "PyObjC.bridgesupport")
        _parseBridgeSupport(data, globals, frameworkName, inlineTab=inlineTab)
        return bundle

    # Look for metadata in the framework bundle
    path = bundle.pathForResource_ofType_inDirectory_(
        frameworkName, "bridgesupport", "BridgeSupport"
    )
    if path is not None:
        dylib_path = bundle.pathForResource_ofType_inDirectory_(
            frameworkName, "dylib", "BridgeSupport"
        )
        with open(path, "rb") as fp:
            data = fp.read()
        if dylib_path is not None:
            _parseBridgeSupport(data, globals, frameworkName, dylib_path=dylib_path)
        else:
            _parseBridgeSupport(data, globals, frameworkName)

        # Check if we have additional metadata bundled with PyObjC
        if resource_exists(frameworkResourceName, "PyObjCOverrides.bridgesupport"):
            data = resource_string(
                frameworkResourceName, "PyObjCOverrides.bridgesupport"
            )
            _parseBridgeSupport(data, globals, frameworkName, inlineTab=inlineTab)

        return bundle

    # If there is no metadata there look for metadata in the standard Library
    # locations
    fn = frameworkName + ".bridgesupport"
    for dn in BRIDGESUPPORT_DIRECTORIES:
        path = os.path.join(dn, fn)
        if os.path.exists(path):
            with open(path, "rb") as fp:
                data = fp.read()  # pragma: no branch

            dylib_path = os.path.join(dn, frameworkName + ".dylib")
            if os.path.exists(dylib_path):
                _parseBridgeSupport(data, globals, frameworkName, dylib_path=dylib_path)
            else:
                _parseBridgeSupport(data, globals, frameworkName)

            # Check if we have additional metadata bundled with PyObjC
            if resource_exists(frameworkResourceName, "PyObjCOverrides.bridgesupport"):
                data = resource_string(
                    frameworkResourceName, "PyObjCOverrides.bridgesupport"
                )
                _parseBridgeSupport(data, globals, frameworkName, inlineTab=inlineTab)

            return bundle

    return bundle
