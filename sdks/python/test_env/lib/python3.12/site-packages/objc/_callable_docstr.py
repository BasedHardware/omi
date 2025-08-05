__all__ = ()
import inspect

import objc
from objc._objc import _nameForSignature

basic_types = {
    objc._C_VOID: "void",
    objc._C_INT: "int",
    objc._C_UINT: "unsigned int",
    objc._C_LNG: "long",
    objc._C_ULNG: "unsigned long",
    objc._C_LNG_LNG: "long long",
    objc._C_ULNG_LNG: "unsigned long long",
    objc._C_FLT: "float",
    objc._C_DBL: "double",
    objc._C_SHT: "short",
    objc._C_USHT: "unsigned short",
    objc._C_CHR: "char",
    objc._C_UCHR: "unsigned char",
    objc._C_CHAR_AS_INT: "int8_t",
    objc._C_CHAR_AS_TEXT: "char",
    objc._C_UNICHAR: "UniChar",
    objc._C_BOOL: "bool",
    objc._C_NSBOOL: "BOOL",
    objc._C_ID: "id",
    objc._C_CLASS: "Class",
    objc._C_SEL: "SEL",
    objc._C_CHARPTR: "char*",
}

prefixes = {
    objc._C_IN: "in ",
    objc._C_OUT: "out ",
    objc._C_INOUT: "inout ",
    objc._C_CONST: "const ",
    objc._C_ONEWAY: "oneway ",
}


def describe_type(typestr):
    nm = basic_types.get(typestr)
    if nm is not None:
        return nm

    if typestr == b"^?":
        return "<FUNCTION>"
    elif typestr == b"@?":
        return "<BLOCK>"

    if typestr.startswith(objc._C_PTR):
        nm = _nameForSignature(typestr)
        if nm is not None:
            return nm
        return describe_type(typestr[1:]) + "*"

    if typestr[:1] in prefixes:
        return prefixes[typestr[:1]] + describe_type(typestr[1:])

    if typestr.startswith(objc._C_STRUCT_B):
        nm = _nameForSignature(typestr)
        if nm is not None:
            return nm

        typestr = typestr[1:]
        idx = typestr.find(b"=")
        if idx == -1:
            return "struct <?>"

        else:
            nm = typestr[:idx]
            if not nm:
                return "struct <?>"
            nm = nm.decode("utf-8").lstrip("_")
            if "." in nm:
                return nm.rsplit(".", 1)[-1]
            return nm

    if typestr.startswith(objc._C_VECTOR_B):
        base_type = basic_types[typestr[-2:-1]]
        if base_type.startswith("unsigned "):
            base_type = "u" + base_type.split()[-1]

        count = typestr[1:-2]
        return f"simd_{base_type}{count.decode()}"

    if typestr.startswith(objc._C_ARY_B):
        typestr = typestr[1:]
        d = b""
        while typestr[:1].isdigit():
            d += typestr[:1]
            typestr = typestr[1:]

        return "{}[{}]".format(describe_type(typestr), d.decode("utf-8"))

    if typestr.startswith(objc._C_UNION_B):
        typestr = typestr[1:]
        idx = typestr.find(b"=")
        if idx == -1:
            return "union <?>"

        else:
            nm = typestr[:idx]
            if not nm:
                nm = b"<?>"
            return "union {}".format(nm.decode("utf-8"))

    return "<?>"


def describe_callable(callable_object):
    if not hasattr(callable_object, "__name__") or not hasattr(
        callable_object, "__metadata__"
    ):
        return None

    name = callable_object.__name__
    try:
        metadata = callable_object.__metadata__()
    except objc.internal_error:
        return None

    return describe_callable_metadata(
        name, metadata, ismethod=isinstance(callable_object, objc.selector)
    )


def describe_callable_metadata(name, metadata, offset="", ismethod=False):
    arg_info = []
    if ismethod:
        arg_offset = 2

        name_parts = name.split(":")
        hdr_name = []
        if len(metadata["arguments"]) > arg_offset:
            for idx, (nm, info) in enumerate(
                zip(name_parts, metadata["arguments"][arg_offset:])
            ):
                if hdr_name:
                    hdr_name.append(" ")
                hdr_name.append(nm)
                hdr_name.append(":(")
                hdr_name.append(describe_type(info["type"]))
                hdr_name.append(")arg%d" % (idx,))

                if info["type"][:1] in prefixes and info["type"][:1] not in (
                    objc._C_ONEWAY,
                    objc._C_CONST,
                ):
                    arg_info.append((idx, info))
                elif info.get("printf_format"):
                    arg_info.append((idx, info))
                elif info.get("callable"):
                    arg_info.append((idx, info))

        else:
            hdr_name.append(name)

        if metadata.get("variadic"):
            hdr_name.append(", ...")

        header = "{} ({}){};".format(
            "+" if metadata["classmethod"] else "-",
            describe_type(metadata["retval"]["type"]),
            "".join(hdr_name),
        )
    else:
        hdr_name = []
        arg_offset = 0
        for idx, info in enumerate(metadata["arguments"]):
            if idx != 0:
                hdr_name.append(", ")
            hdr_name.append(describe_type(info["type"]))
            hdr_name.append(" arg%d" % (idx,))
            if info["type"][:1] in prefixes and info["type"][:1] not in (
                objc._C_ONEWAY,
                objc._C_CONST,
            ):
                arg_info.append((idx, info))
            elif info.get("printf_format"):
                arg_info.append((idx, info))
            elif info.get("callable"):
                arg_info.append((idx, info))
        if metadata.get("variadic"):
            hdr_name.append(", ...")

        if not hdr_name:
            hdr_name.append("void")

        header = "{} {}({});".format(
            describe_type(metadata["retval"]["type"]),
            name,
            "".join(hdr_name),
        )

    result = [header]
    if metadata.get("suggestion"):
        result.append("")
        result.append("WARNING: {}".format(metadata["suggestion"]))

    if arg_info:
        result.append("")
        for idx, info in arg_info:
            if info.get("printf_format"):
                result.append("arg%d: %%-style format string" % (idx,))
                continue

            elif info.get("callable"):
                result.append(
                    "arg%d: %s"
                    % (
                        idx,
                        describe_callable_metadata(
                            "callback", info["callable"], offset="    " + offset
                        ),
                    )
                )
                continue

            else:
                arg = info.get("c_array_length_in_arg")
                if arg is not None:
                    if isinstance(arg, tuple):
                        result.append(
                            "arg%d: array with length on input in arg%d, "
                            "and output in arg%d"
                            % (idx, arg[0] - arg_offset, arg[1] - arg_offset)
                        )
                    else:
                        if info.get("c_array_length_in_result"):
                            result.append(
                                "arg%d: array with length on input in arg%d, "
                                "and output in return value" % (idx, arg - arg_offset)
                            )
                        else:
                            result.append(
                                "arg%d: array with length in arg%d"
                                % (idx, arg - arg_offset)
                            )
                    continue

                if info.get("c_array_length_in_result"):
                    result.append("arg%d: array with length in return value" % (idx,))
                    continue

                if info.get("c_array_of_fixed_length"):
                    result.append(
                        "arg%d: array with length %d"
                        % (idx, info.get("c_array_of_fixed_length"))
                    )
                    continue

                if info.get("c_array_of_variable_length"):
                    result.append("arg%d: array with unknown length" % (idx,))
                    continue

                if info.get("c_array_delimited_by_null"):
                    result.append(
                        "arg%d: array (will be NULL terminated in C)" % (idx,)
                    )
                    continue

                result.append(
                    "arg%d: pass-by-reference %sargument"
                    % (idx, prefixes.get(info["type"][:1]))
                )

    if len(metadata["arguments"]) > arg_offset:
        if metadata.get("variadic") and metadata.get("c_array_delimited_by_null"):
            if not arg_info:
                result.append("")

            result.append(
                "Variadic arguments form an array of C type %s"
                % (describe_type(metadata["arguments"][-1]["type"]),)
            )

    if metadata.get("__doc__", None):
        result.append("\n")
        result.append(str(metadata["__doc__"]))

    return ("\n" + offset).join(result).replace("\n" + offset + "\n", "\n\n")


objc.options._callable_doc = describe_callable


def callable_signature(callable_object):
    # Create an inspect.Signature for an PyObjC callable
    # both objc.function and objc.native_selector only support positional
    # arguments, and not keyword arguments.
    if not hasattr(callable_object, "__name__") or not hasattr(
        callable_object, "__metadata__"
    ):
        return None

    try:
        metadata = callable_object.__metadata__()
    except objc.internal_error:
        # This can happen with some private methods with undocumented
        # characters in type encodings
        return None

    ismethod = isinstance(callable_object, objc.selector)
    isimp = isinstance(callable_object, objc.IMP)

    if ismethod:
        # Skip 'self' and 'selector' implicit arguments
        args = metadata["arguments"][2:]
    elif isimp:
        # Ignore the 'selector' argument
        args = (metadata["arguments"][0],) + metadata["arguments"][2:]
    else:
        args = metadata["arguments"]

    parameters = []
    for idx, _arg in enumerate(args):
        p_name = "arg%d" % (idx,)
        parameters.append(inspect.Parameter(p_name, inspect.Parameter.POSITIONAL_ONLY))

    return inspect.Signature(parameters)


objc.options._callable_signature = callable_signature
