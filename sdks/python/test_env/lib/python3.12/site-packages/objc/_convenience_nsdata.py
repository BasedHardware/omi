"""
Specific support for NSData.

NSData needs to be handles specially for correctness reasons,
and is therefore in the core instead of the Foundation
framework wrappers.
"""

from objc._convenience import addConvenienceForClass
from objc._objc import registerMetaDataForSelector
from ._new import NEW_MAP
import sys
import operator

registerMetaDataForSelector(
    b"NSData",
    b"dataWithBytes:length:",
    {
        "arguments": {
            2: {"type": b"^v", "type_modifier": b"n", "c_array_length_in_arg": 3}
        }
    },
)
registerMetaDataForSelector(
    b"NSData",
    b"initWithBytes:length:",
    {
        "arguments": {
            2: {"type": b"^v", "type_modifier": b"n", "c_array_length_in_arg": 3}
        }
    },
)
registerMetaDataForSelector(
    b"NSData",
    b"replaceBytesInRange:withBytes:length:",
    {
        "arguments": {
            3: {"type": b"^v", "type_modifier": b"n", "c_array_length_in_arg": 4}
        }
    },
)


def nsdata__new__(cls, value=None):
    if value is None:
        return cls.data()

    else:
        try:
            view = memoryview(value)
        except TypeError:
            view = bytes(value)

        return cls.dataWithBytes_length_(view, len(view))


for cls in ("NSData", "NSMutableData"):
    NEW_MAP.setdefault(cls, {})[()] = nsdata__new__


def nsdata__str__(self):
    if len(self) == 0:
        return str(b"")
    return str(self.bytes().tobytes())


def nsdata__bytes__(self):
    return bytes(self.bytes())


def nsdata__getitem__(self, item):
    buff = self.bytes()
    return buff[item]


# The method implementations below are a bit simplistic,
# but should be "good enough" for most usages of these
# APIs. Cocoa does not have equivalent methods.
def nsdata_capitalize(self):
    return bytes(self.bytes()).capitalize()


def nsdata_center(self, *args, **kwds):
    return bytes(self.bytes()).center(*args, **kwds)


def nsdata_count(self, *args, **kwds):
    return bytes(self.bytes()).count(*args, **kwds)


def nsdata_decode(self, *args, **kwds):
    return bytes(self.bytes()).decode(*args, **kwds)


def nsdata_endswith(self, *args, **kwds):
    return bytes(self.bytes()).endswith(*args, **kwds)


def nsdata_expandtabs(self, *args, **kwds):
    return bytes(self.bytes()).expandtabs(*args, **kwds)


def nsdata_find(self, *args, **kwds):
    return bytes(self.bytes()).find(*args, **kwds)


def nsdata_fromhex(cls, *args, **kwds):
    return cls.dataWithData_(bytes.fromhex(*args, **kwds))


def nsdata_hex(self, *args, **kwds):
    return memoryview(self.bytes()).hex(*args, **kwds)


def nsdata_index(self, *args, **kwds):
    return bytes(self.bytes()).index(*args, **kwds)


def nsdata_isalnum(self, *args, **kwds):
    return bytes(self.bytes()).isalnum(*args, **kwds)


def nsdata_isalpha(self, *args, **kwds):
    return bytes(self.bytes()).isalpha(*args, **kwds)


def nsdata_isdigit(self, *args, **kwds):
    return bytes(self.bytes()).isdigit(*args, **kwds)


def nsdata_islower(self, *args, **kwds):
    return bytes(self.bytes()).islower(*args, **kwds)


def nsdata_isspace(self, *args, **kwds):
    return bytes(self.bytes()).isspace(*args, **kwds)


def nsdata_istitle(self, *args, **kwds):
    return bytes(self.bytes()).istitle(*args, **kwds)


def isdata_isupper(self, *args, **kwds):
    return bytes(self.bytes()).isupper(*args, **kwds)


def nsdata_join(self, *args, **kwds):
    return bytes(self.bytes()).join(*args, **kwds)


def nsdata_ljust(self, *args, **kwds):
    return bytes(self.bytes()).ljust(*args, **kwds)


def nsdata_lower(self, *args, **kwds):
    return bytes(self.bytes()).lower(*args, **kwds)


def nsdata_lstrip(self, *args, **kwds):
    return bytes(self.bytes()).lstrip(*args, **kwds)


def nsdata_maketrans(cls, *args, **kwds):
    return bytes.maketrans(*args, **kwds)


def nsdata_partition(self, *args, **kwds):
    return bytes(self.bytes()).partition(*args, **kwds)


def nsdata_replace(self, *args, **kwds):
    return bytes(self.bytes()).replace(*args, **kwds)


def nsdata_rfind(self, *args, **kwds):
    return bytes(self.bytes()).rfind(*args, **kwds)


def nsdata_rindex(self, *args, **kwds):
    return bytes(self.bytes()).rindex(*args, **kwds)


def nsdata_rjust(self, *args, **kwds):
    return bytes(self.bytes()).rjust(*args, **kwds)


def nsdata_rpartition(self, *args, **kwds):
    return bytes(self.bytes()).rpartition(*args, **kwds)


def nsdata_rsplit(self, *args, **kwds):
    return bytes(self.bytes()).rsplit(*args, **kwds)


def nsdata_rstrip(self, *args, **kwds):
    return bytes(self.bytes()).rstrip(*args, **kwds)


def nsdata_split(self, *args, **kwds):
    return bytes(self.bytes()).split(*args, **kwds)


def nsdata_splitlines(self, *args, **kwds):
    return bytes(self.bytes()).splitlines(*args, **kwds)


def nsdata_startswith(self, *args, **kwds):
    return bytes(self.bytes()).startswith(*args, **kwds)


def nsdata_strip(self, *args, **kwds):
    return bytes(self.bytes()).strip(*args, **kwds)


def nsdata_swapcase(self, *args, **kwds):
    return bytes(self.bytes()).swapcase(*args, **kwds)


def nsdata_title(self, *args, **kwds):
    return bytes(self.bytes()).title(*args, **kwds)


def nsdata_translate(self, *args, **kwds):
    return bytes(self.bytes()).translate(*args, **kwds)


def nsdata_upper(self, *args, **kwds):
    return bytes(self.bytes()).upper(*args, **kwds)


def nsdata_zfill(self, *args, **kwds):
    return bytes(self.bytes()).zfill(*args, **kwds)


def nsdata__mul__(self, count):
    if count <= 0:
        return b""
    else:
        return bytes(self) * count


def nsdata__add__(self, other):
    return bytes(self) + other


def nsdata__radd__(self, other):
    return other + bytes(self)


def nsdata_isascii(self, *args, **kwds):
    return bytes(self.bytes()).isascii(*args, **kwds)


addConvenienceForClass(
    "NSData",
    (
        ("__len__", lambda self: self.length()),
        ("__str__", nsdata__str__),
        ("__getitem__", nsdata__getitem__),
        ("__bytes__", nsdata__bytes__),
        ("__mul__", nsdata__mul__),
        ("__rmul__", nsdata__mul__),
        ("__add__", nsdata__add__),
        ("__radd__", nsdata__radd__),
        ("capitalize", nsdata_capitalize),
        ("center", nsdata_center),
        ("count", nsdata_count),
        ("decode", nsdata_decode),
        ("endswith", nsdata_endswith),
        ("expandtabs", nsdata_expandtabs),
        ("find", nsdata_find),
        ("fromhex", classmethod(nsdata_fromhex)),
        ("hex", nsdata_hex),
        ("index", nsdata_index),
        ("isalnum", nsdata_isalnum),
        ("isalpha", nsdata_isalpha),
        ("isascii", nsdata_isascii),
        ("isdigit", nsdata_isdigit),
        ("islower", nsdata_islower),
        ("isspace", nsdata_isspace),
        ("istitle", nsdata_istitle),
        ("isupper", isdata_isupper),
        ("join", nsdata_join),
        ("ljust", nsdata_ljust),
        ("lower", nsdata_lower),
        ("lstrip", nsdata_lstrip),
        ("maketrans", classmethod(nsdata_maketrans)),
        ("partition", nsdata_partition),
        ("replace", nsdata_replace),
        ("rfind", nsdata_rfind),
        ("rindex", nsdata_rindex),
        ("rjust", nsdata_rjust),
        ("rpartition", nsdata_rpartition),
        ("rsplit", nsdata_rsplit),
        ("rstrip", nsdata_rstrip),
        ("split", nsdata_split),
        ("splitlines", nsdata_splitlines),
        ("startswith", nsdata_startswith),
        ("strip", nsdata_strip),
        ("swapcase", nsdata_swapcase),
        ("title", nsdata_title),
        ("translate", nsdata_translate),
        ("upper", nsdata_upper),
        ("zfill", nsdata_zfill),
    ),
)

if sys.version_info[:2] >= (3, 9):  # pragma: no branch

    def nsdata_removeprefix(self, *args, **kwds):
        return bytes(self.bytes()).removeprefix(*args, **kwds)

    def nsdata_removesuffix(self, *args, **kwds):
        return bytes(self.bytes()).removesuffix(*args, **kwds)

    addConvenienceForClass(
        "NSData",
        (
            ("removeprefix", nsdata_removeprefix),
            ("removesuffix", nsdata_removesuffix),
        ),
    )


def nsmutabledata__setitem__(self, item, value):
    self.mutableBytes()[item] = value


def nsmutabledata__delitem__(self, item):
    if isinstance(item, slice):
        start, stop, step = item.indices(len(self))
        if step == 1:
            self.replaceBytesInRange_withBytes_length_((start, stop - start), b"", 0)
        else:
            indices = range(start, stop, step)
            if step > 0:
                for idx in indices[::-1]:
                    self.replaceBytesInRange_withBytes_length_((idx, 1), b"", 0)
            else:
                for idx in indices:
                    self.replaceBytesInRange_withBytes_length_((idx, 1), b"", 0)
    else:
        item = operator.index(item)
        if item < 0:
            item += len(self)
            if item < 0:
                raise IndexError(f"{type(self).__name__} index out of range")
        self.replaceBytesInRange_withBytes_length_((item, 1), b"", 0)


def nsmutabledata__iadd__(self, iterable_of_ints):
    view = memoryview(iterable_of_ints)
    self.appendData_(view)

    return self


def nsmutabledata_extend(self, iterable_of_ints):
    try:
        view = memoryview(iterable_of_ints)
    except TypeError:
        self.appendData_(bytes(iterable_of_ints))
    else:
        self.appendData_(view)

    return self


def nsmutabledata__imul__(self, count):
    if count <= 0:
        self.clear()
        return self
    elif count == 1:
        return self

    else:
        orig = self.copy()
        for _ in range(count - 1):
            self += orig
        return self


def nsmutabledata_reverse(self):
    value = bytes(self)[::-1]
    self.setData_(value)


def nsmutabledata_pop(self, index=-1):
    index = operator.index(index)

    if index < 0:
        index += len(self)
        if index < 0:
            raise IndexError(f"{type(self).__name__} index out of range")

    result = self[index]
    self.replaceBytesInRange_withBytes_length_((index, 1), b"", 0)
    return result


def nsmutabledata_remove(self, value):
    value = operator.index(value)
    value = value.to_bytes(1, "little")
    rng = self.rangeOfData_options_range_(value, 0, (0, len(self)))
    if rng[1] == 0:
        return
    self.replaceBytesInRange_withBytes_length_(rng, b"", 0)


def nsmutabledata_insert(self, index, value):
    value = operator.index(value)
    value = value.to_bytes(1, "little")
    self.replaceBytesInRange_withBytes_length_((index, 0), value, len(value))


def nsmutabledata_append(self, value):
    value = operator.index(value)
    self += bytes([value])


def nsmutabledata_clear(self):
    self.setData_(b"")


addConvenienceForClass(
    "NSMutableData",
    (
        ("__setitem__", nsmutabledata__setitem__),
        ("__delitem__", nsmutabledata__delitem__),
        ("__iadd__", nsmutabledata__iadd__),
        ("__imul__", nsmutabledata__imul__),
        ("extend", nsmutabledata_extend),
        ("append", nsmutabledata_append),
        ("reverse", nsmutabledata_reverse),
        ("remove", nsmutabledata_remove),
        ("clear", nsmutabledata_clear),
        ("pop", nsmutabledata_pop),
        ("insert", nsmutabledata_insert),
    ),
)
