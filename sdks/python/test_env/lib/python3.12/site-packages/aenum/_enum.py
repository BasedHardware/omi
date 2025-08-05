from __future__ import print_function
from ._common import *
from ._constant import NamedConstant
from ._tuple import NamedTuple
from collections import defaultdict
import sys as _sys

__all__ = [
        'bit_count', 'is_single_bit', 'bin', 'property', 'bits',
        'AddValue', 'MagicValue', 'MultiValue', 'NoAlias', 'Unique', 'enum', 'auto',
        'AddValueEnum', 'MultiValueEnum', 'NoAliasEnum', 'UniqueEnum', 'AutoNumberEnum',
        'OrderedEnum', 'unique', 'no_arg', 'extend_enum', 'enum_property',
        'EnumType', 'EnumMeta', 'EnumDict', 'Enum', 'IntEnum', 'StrEnum', 'Flag', 'IntFlag',
        'LowerStrEnum', 'UpperStrEnum', 'ReprEnum', 'SqliteEnum', 'sqlite3',
        'FlagBoundary', 'STRICT', 'CONFORM', 'EJECT', 'KEEP',
        'add_stdlib_integration', 'remove_stdlib_integration',
        'export', 'cls2module', '_reduce_ex_by_name', 'show_flag_values',
        ]
        

_bltin_bin = bin

try:
    import sqlite3
except ImportError:
    sqlite3 = None
    __all__.remove('SqliteEnum')

try:
    RecursionError
except NameError:
    # python3.4
    RecursionError = RuntimeError


try:
    any
except NameError:
    def any(iterable):
        for element in iterable:
            if element:
                return True
        return False

# derive from stdlib enum if possible
stdlib_enums = ()
try:
    import enum
    if hasattr(enum, 'version'):
        raise ImportError('wrong version')
    else:
        from enum import EnumMeta as StdlibEnumMeta, Enum as StdlibEnum, IntEnum as StdlibIntEnum
        StdlibFlag = StdlibIntFlag = StdlibStrEnum = StdlibReprEnum = None
        stdlib_enums = StdlibEnum, StdlibIntEnum
except ImportError:
    StdlibEnumMeta = StdlibEnum = StdlibIntEnum = StdlibIntFlag = StdlibFlag = StdlibStrEnum = StdlibStrEnum = StdlibReprEnum = None

if StdlibEnum:
    try:
        from enum import IntFlag as StdlibIntFlag, Flag as StdlibFlag
        stdlib_enums += StdlibFlag, StdlibIntFlag
    except ImportError:
        pass
    try:
        from enum import StrEnum as StdlibStrEnum
        stdlib_enums += (StdlibStrEnum, )
    except ImportError:
        pass
    try:
        from enum import ReprEnum as StdlibReprEnum
        stdlib_enums += (StdlibReprEnum, )
    except ImportError:
        pass

# will be exported later
MagicValue = AddValue = MultiValue = NoAlias = Unique = None

def export(collection, namespace=None):
    """
    export([collection,] namespace) -> Export members to target namespace.

    If collection is not given, act as a decorator.
    """
    if namespace is None:
        namespace = collection
        def export_decorator(collection):
            return export(collection, namespace)
        return export_decorator
    elif issubclass(collection, NamedConstant):
        for n, c in collection.__dict__.items():
            if isinstance(c, NamedConstant):
                namespace[n] = c
    elif issubclass(collection, Enum) or stdlib_enums and issubclass(collection, stdlib_enums):
        data = collection.__members__.items()
        for n, m in data:
            namespace[n] = m
    else:
        raise TypeError('%r is not a supported collection' % (collection,) )
    return collection

def bit_count(num):
    """
    return number of set bits

    Counting bits set, Brian Kernighan's way*

        unsigned int v;          // count the number of bits set in v
        unsigned int c;          // c accumulates the total bits set in v
        for (c = 0; v; c++)
        {   v &= v - 1;  }       //clear the least significant bit set

    This method goes through as many iterations as there are set bits. So if we
    have a 32-bit word with only the high bit set, then it will only go once
    through the loop.

    * The C Programming Language 2nd Ed., Kernighan & Ritchie, 1988.

    This works because each subtraction "borrows" from the lowest 1-bit. For
    example:

          loop pass 1     loop pass 2
          -----------     -----------
               101000          100000
             -      1        -      1
             = 100111        = 011111
             & 101000        & 100000
             = 100000        =      0

    It is an excellent technique for Python, since the size of the integer need
    not be determined beforehand.

    (from https://wiki.python.org/moin/BitManipulation)
    """
    count = 0
    while num:
        num &= num - 1
        count += 1
    return count

def is_single_bit(value):
    """
    True if only one bit set in value (should be an int)
    """
    if value == 0:
        return False
    value &= value - 1
    return value == 0

def _iter_bits_lsb(value):
    """
    Return each bit value one at a time.

    >>> list(_iter_bits_lsb(6))
    [2, 4]
    """

    while value:
        bit = value & (~value + 1)
        yield bit
        value ^= bit

def bin(value, max_bits=None):
    """
    Like built-in bin(), except negative values are represented in
    twos-compliment, and the leading bit always indicates sign
    (0=positive, 1=negative).

    >>> bin(10)
    '0b0 1010'
    >>> bin(~10)   # ~10 is -11
    '0b1 0101'
    """

    ceiling = 2 ** (value).bit_length()
    if value >= 0:
        s = _bltin_bin(value + ceiling).replace('1', '0', 1)
    else:
        s = _bltin_bin(~value ^ (ceiling - 1) + ceiling)
    sign = s[:3]
    digits = s[3:]
    if not digits:
        digits = '0'
    if max_bits is not None:
        if len(digits) < max_bits:
            digits = (sign[-1] * max_bits + digits)[-max_bits:]
    return "%s %s" % (sign, digits)

def show_flag_values(value):
    return list(_iter_bits_lsb(value))


try:
    from types import DynamicClassAttribute
    base = DynamicClassAttribute
except ImportError:
    base = object
    DynamicClassAttribute = None

class property(base):
    """
    This is a descriptor, used to define attributes that act differently
    when accessed through an enum member and through an enum class.
    Instance access is the same as property(), but access to an attribute
    through the enum class will look in the class' _member_map_.
    """

    # inherit from DynamicClassAttribute if we can in order to get `inspect`
    # support

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
        # next two lines make property act the same as bltin_property
        self.__doc__ = doc or fget.__doc__
        self.overwrite_doc = doc is None
        # support for abstract methods
        self.__isabstractmethod__ = bool(getattr(fget, '__isabstractmethod__', False))
        # names, if possible

    def getter(self, fget):
        fdoc = fget.__doc__ if self.overwrite_doc else None
        result = type(self)(fget, self.fset, self.fdel, fdoc or self.__doc__)
        result.overwrite_doc = self.__doc__ is None
        return result

    def setter(self, fset):
        fdoc = fget.__doc__ if self.overwrite_doc else None
        result = type(self)(self.fget, fset, self.fdel, self.__doc__)
        result.overwrite_doc = self.__doc__ is None
        return result

    def deleter(self, fdel):
        fdoc = fget.__doc__ if self.overwrite_doc else None
        result = type(self)(self.fget, self.fset, fdel, self.__doc__)
        result.overwrite_doc = self.__doc__ is None
        return result

    def __repr__(self):
        member = self.ownerclass._member_map_.get(self.name)
        func = self.fget or self.fset or self.fdel
        strings = []
        if member:
            strings.append('%r' % member)
        if func:
            strings.append('function=%s' % func.__name__)
        return 'property(%s)' % ', '.join(strings)

    def __get__(self, instance, ownerclass=None):
        if instance is None:
            try:
                return ownerclass._member_map_[self.name]
            except KeyError:
                raise AttributeError(
                        '%r has no attribute %r' % (ownerclass, self.name)
                        )
        else:
            if self.fget is not None:
                return self.fget(instance)
            else:
                if self.fset is not None:
                    raise AttributeError(
                            'cannot read attribute %r on %r' % (self.name, ownerclass)
                            )
                else:
                    try:
                        return instance.__dict__[self.name]
                    except KeyError:
                        raise AttributeError(
                                '%r member has no attribute %r' % (ownerclass, self.name)
                                )

    def __set__(self, instance, value):
        if self.fset is None:
            if self.fget is not None:
                raise AttributeError(
                        "cannot set attribute %r on <aenum %r>" % (self.name, self.clsname)
                        )
            else:
                instance.__dict__[self.name] = value
        else:
            return self.fset(instance, value)

    def __delete__(self, instance):
        if self.fdel is None:
            if self.fget or self.fset:
                raise AttributeError(
                        "cannot delete attribute %r on <aenum %r>" % (self.name, self.clsname)
                        )
            elif self.name in instance.__dict__:
                del instance.__dict__[self.name]
            else:
                raise AttributeError(
                        "no attribute %r on <aenum %r> member" % (self.name, self.clsname)
                        )
        else:
            return self.fdel(instance)

    def __set_name__(self, ownerclass, name):
        self.name = name
        self.clsname = ownerclass.__name__
        self.ownerclass = ownerclass

_RouteClassAttributeToGetattr = property
if DynamicClassAttribute is None:
    DynamicClassAttribute = property
# deprecated
enum_property = property

# more helpers

class SentinelType(type):
    def __repr__(cls):
        return '<%s>' % cls.__name__
Sentinel = SentinelType('Sentinel', (object, ), {})

def _power_of_two(value):
    if value < 1:
        return False
    return value == 2 ** _high_bit(value)

def bits(num):
    if num in (0, 1):
        return str(num)
    negative = False
    if num < 0:
        negative = True
        num = ~num
    result = bits(num>>1) + str(num&1)
    if negative:
        result = '1' + ''.join(['10'[d=='1'] for d in result])
    return result


def bit_count(num):
    """
        return number of set bits

        Counting bits set, Brian Kernighan's way*

            unsigned int v;          // count the number of bits set in v
            unsigned int c;          // c accumulates the total bits set in v
            for (c = 0; v; c++)
            {   v &= v - 1;  }       //clear the least significant bit set

        This method goes through as many iterations as there are set bits. So if we
        have a 32-bit word with only the high bit set, then it will only go once
        through the loop.

        * The C Programming Language 2nd Ed., Kernighan & Ritchie, 1988.

        This works because each subtraction "borrows" from the lowest 1-bit. For example:

              loop pass 1     loop pass 2
              -----------     -----------
                   101000          100000
                 -      1        -      1
                 = 100111        = 011111
                 & 101000        & 100000
                 = 100000        =      0

        It is an excellent technique for Python, since the size of the integer need not
        be determined beforehand.
    """
    count = 0
    while(num):
        num &= num - 1
        count += 1
    return(count)

def bit_len(num):
    length = 0
    while num:
        length += 1
        num >>= 1
    return length

def is_single_bit(num):
    """
    True if only one bit set in num (should be an int)
    """
    return (num != 0) and (num & (num - 1)) == 0

def _check_auto_args(method):
    """check if new generate method supports *args and **kwds"""
    if isinstance(method, staticmethod):
        method = method.__get__(type)
    method = getattr(method, 'im_func', method)
    args, varargs, keywords, defaults = getargspec(method)
    return varargs is not None and keywords is not None

def enumsort(things):
    """
    sorts things by value if all same type; otherwise by name
    """
    if not things:
        return things
    sort_type = type(things[0])
    if not issubclass(sort_type, tuple):
        # direct sort or type error
        if not all((type(v) is sort_type) for v in things[1:]):
            raise TypeError('cannot sort items of different types')
        return sorted(things)
    else:
        # expecting list of (name, value) tuples
        sort_type = type(things[0][1])
        try:
            if all((type(v[1]) is sort_type) for v in things[1:]):
                return sorted(things, key=lambda i: i[1])
            else:
                raise TypeError('try name sort instead')
        except TypeError:
            return sorted(things, key=lambda i: i[0])

# Enum

    # _init_ and value and AddValue
    # -----------------------------
    # by default, when defining a member everything after the = is "the value", everything is
    #   passed to __new__, everything is passed to __init__
    #
    # if _init_ is present then
    #   if `value` is not in _init_, everything is "the value", defaults apply
    #   if `value` is in _init_, only the first thing after the = is the value, and the rest will
    #       be passed to __init__
    #   if fewer values are present for member assignment than _init_ calls for, _generate_next_value_
    #       will be called in an attempt to generate them
    #
    # if AddValue is present then
    #   _generate_next_value_ is always called, and any generated values are prepended to provided
    #       values (custom _gnv_s can change that)
    #   default _init_ rules apply


    # Constants used in Enum

@export(globals())
class EnumConstants(NamedConstant):
    AddValue = constant('addvalue', 'prepends value(s) from _generate_next_value_ to each member')
    MagicValue = constant('magicvalue', 'calls _generate_next_value_ when no arguments are given')
    MultiValue = constant('multivalue', 'each member can have several values')
    NoAlias = constant('noalias', 'duplicate valued members are distinct, not aliased')
    Unique = constant('unique', 'duplicate valued members are not allowed')
    def __repr__(self):
        return self._name_


    # Dummy value for Enum as EnumType explicity checks for it, but of course until
    # EnumType finishes running the first time the Enum class doesn't exist.  This
    # is also why there are checks in EnumType like `if Enum is not None`.
    #
    # Ditto for Flag.

Enum = ReprEnum = IntEnum = StrEnum = Flag = IntFlag = EJECT = KEEP = None

class enum(object):
    """
    Helper class to track args, kwds.
    """
    def __init__(self, *args, **kwds):
        self._args = args
        self._kwds = dict(kwds.items())
        self._hash = hash(args)
        self.name = None

    @bltin_property
    def args(self):
        return self._args

    @bltin_property
    def kwds(self):
        return self._kwds.copy()

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.args == other.args and self.kwds == other.kwds

    def __ne__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.args != other.args or self.kwds != other.kwds

    def __repr__(self):
        final = []
        args = ', '.join(['%r' % (a, ) for a in self.args])
        if args:
            final.append(args)
        kwds = ', '.join([('%s=%r') % (k, v) for k, v in enumsort(list(self.kwds.items()))])
        if kwds:
            final.append(kwds)
        return '%s(%s)' % (self.__class__.__name__, ', '.join(final))

_auto_null = SentinelType('no_value', (object, ), {})
class auto(enum):
    """
    Instances are replaced with an appropriate value in Enum class suites.
    """
    enum_member = _auto_null
    _value = _auto_null
    _operations = []

    def __and__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_and_, (self, other)))
        return new_auto

    def __rand__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_and_, (other, self)))
        return new_auto

    def __invert__(self):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_inv_, (self,)))
        return new_auto

    def __or__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_or_, (self, other)))
        return new_auto

    def __ror__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_or_, (other, self)))
        return new_auto

    def __xor__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_xor_, (self, other)))
        return new_auto

    def __rxor__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_xor_, (other, self)))
        return new_auto

    def __abs__(self):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_abs_, (self, )))
        return new_auto

    def __add__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_add_, (self, other)))
        return new_auto

    def __radd__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_add_, (other, self)))
        return new_auto

    def __neg__(self):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_neg_, (self, )))
        return new_auto

    def __pos__(self):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_pos_, (self, )))
        return new_auto

    if PY2:
        def __div__(self, other):
            new_auto = self.__class__()
            new_auto._operations = self._operations[:]
            new_auto._operations.append((_div_, (self, other)))
            return new_auto

    def __rdiv__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_div_, (other, self)))
        return new_auto

    def __floordiv__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_floordiv_, (self, other)))
        return new_auto

    def __rfloordiv__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_floordiv_, (other, self)))
        return new_auto

    def __truediv__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_truediv_, (self, other)))
        return new_auto

    def __rtruediv__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_truediv_, (other, self)))
        return new_auto

    def __lshift__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_lshift_, (self, other)))
        return new_auto

    def __rlshift__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_lshift_, (other, self)))
        return new_auto

    def __rshift__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_rshift_, (self, other)))
        return new_auto

    def __rrshift__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_rshift_, (other, self)))
        return new_auto

    def __mod__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_mod_, (self, other)))
        return new_auto

    def __rmod__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_mod_, (other, self)))
        return new_auto

    def __mul__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_mul_, (self, other)))
        return new_auto

    def __rmul__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_mul_, (other, self)))
        return new_auto

    def __pow__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_pow_, (self, other)))
        return new_auto

    def __rpow__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_pow_, (other, self)))
        return new_auto

    def __sub__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_sub_, (self, other)))
        return new_auto

    def __rsub__(self, other):
        new_auto = self.__class__()
        new_auto._operations = self._operations[:]
        new_auto._operations.append((_sub_, (other, self)))
        return new_auto

    def __repr__(self):
        if self._operations:
            return 'auto(...)'
        else:
            return 'auto(%r, *%r, **%r)' % (self._value, self._args, self._kwds)

    @bltin_property
    def value(self):
        if self._value is not _auto_null and self._operations:
            raise TypeError('auto() object out of sync')
        elif self._value is _auto_null and not self._operations:
            return self._value
        elif self._value is not _auto_null:
            return self._value
        else:
            return self._resolve()

    @value.setter
    def value(self, value):
        if self._operations:
            value = self._resolve(value)
        self._value = value

    def _resolve(self, base_value=None):
            cls = self.__class__
            for op, params in self._operations:
                values = []
                for param in params:
                    if isinstance(param, cls):
                        if param.value is _auto_null:
                            if base_value is None:
                                return _auto_null
                            else:
                                values.append(base_value)
                        else:
                            values.append(param.value)
                    else:
                        values.append(param)
                value = op(*values)
            self._operations[:] = []
            self._value = value
            return value

from . import _common
_common.property = property
_common.auto = auto
del _common


class _EnumArgSpec(NamedTuple):
    args = 0, 'all args except *args and **kwds'
    varargs = 1, 'the name of the *args variable'
    keywords = 2, 'the name of the **kwds variable'
    defaults = 3, 'any default values'
    required = 4, 'number of required values (no default available)'

    def __new__(cls, _new_func):
        argspec = getargspec(_new_func)
        args, varargs, keywords, defaults = argspec
        if defaults:
            reqs = args[1:-len(defaults)]
        else:
            reqs = args[1:]
        return tuple.__new__(_EnumArgSpec, (args, varargs, keywords, defaults, reqs))


class _proto_member:
    """
    intermediate step for enum members between class execution and final creation
    """

    def __init__(self, value):
        self.value = value

    def __set_name__(self, enum_class, member_name):
        """
        convert each quasi-member into an instance of the new enum class
        """
        # first step: remove ourself from enum_class
        delattr(enum_class, member_name)
        # second step: create member based on enum_class
        value = self.value
        kwds = {}
        args = ()
        init_args = ()
        extra_mv_args = ()
        multivalue = None
        if isinstance(value, tuple) and value and isinstance(value[0], auto):
            multivalue = value
            value = value[0]
        if isinstance(value, auto) and value.value is _auto_null:
            args = value.args
            kwds = value.kwds
        elif isinstance(value, auto):
            kwds = value.kwds
            args = (value.value, ) + value.args
            value = value.value
        elif isinstance(value, enum):
            args = value.args
            kwds = value.kwds
        elif isinstance(value, Member):
            value = value.value
            args = (value, )
        elif not isinstance(value, tuple):
            args = (value, )
        else:
            args = value
        if multivalue is not None:
            value = (value, ) + multivalue[1:]
            kwds = {}
            args = value
            del multivalue
        # possibilities
        #
        # - no init, multivalue  -> __new__[0], __init__(*[:]), extra=[1:]
        # - init w/o value, multivalue  -> __new__[0], __init__(*[:]), extra=[1:]
        #
        # - init w/value, multivalue  -> __new__[0], __init__(*[1:]),  extra=[1:]
        #
        # - init w/value, no multivalue  -> __new__[0], __init__(*[1:]), extra=[]
        #
        # - init w/o value, no multivalue  -> __new__[:], __init__(*[:]), extra=[]
        # - no init, no multivalue  ->  __new__[:], __init__(*[:]), extra=[]
        if enum_class._multivalue_ or 'value' in enum_class._creating_init_:
            if enum_class._multivalue_:
                # when multivalue is True, creating_init can be anything
                mv_arg = args[0]
                extra_mv_args = args[1:]
                if 'value' in enum_class._creating_init_:
                    init_args = args[1:]
                else:
                    init_args = args
                args = args[0:1]
                value = args[0]
            else:
                # 'value' is definitely in creating_init
                if enum_class._auto_init_ and enum_class._new_args_:
                    # we have a custom __new__ and an auto __init__
                    # divvy up according to number of params in each
                    init_args = args[-len(enum_class._creating_init_)+1:]
                    if not enum_class._auto_args_:
                        args = args[:len(enum_class._new_args_.args)]
                    value = args[0]
                elif enum_class._auto_init_:
                    # don't pass in value
                    init_args = args[1:]
                    args = args[0:1]
                    value = args[0]
                elif enum_class._new_args_:
                    # do not modify args
                    value = args[0]
                else:
                    # keep all args for user-defined __init__
                    # keep value as-is
                    init_args = args
        else:
            # either no creating_init, or it doesn't have 'value'
            init_args = args
        if enum_class._member_type_ is tuple:   # special case for tuple enums
            args = (args, )     # wrap it one more time
        if not enum_class._use_args_:
            enum_member = enum_class._new_member_(enum_class)
        else:
            enum_member = enum_class._new_member_(enum_class, *args, **kwds)
        if not hasattr(enum_member, '_value_'):
            if enum_class._member_type_ is object:
                enum_member._value_ = value
            else:
                try:
                    enum_member._value_ = enum_class._member_type_(*args, **kwds)
                except Exception as exc:
                    te = TypeError('_value_ not set in __new__, unable to create it')
                    te.__cause__ = exc
                    raise te
        value = enum_member._value_
        enum_member._name_ = member_name
        enum_member.__objclass__ = enum_class
        enum_member.__init__(*init_args, **kwds)
        enum_member._sort_order_ = len(enum_class._member_names_)

        if Flag is not None and issubclass(enum_class, Flag):
            enum_class._flag_mask_ |= value
            if is_single_bit(value):
                enum_class._singles_mask_ |= value
            enum_class._all_bits_ = 2 ** ((enum_class._flag_mask_).bit_length()) - 1

        # If another member with the same value was already defined, the
        # new member becomes an alias to the existing one.
        if enum_class._noalias_:
            # unless NoAlias was specified
            enum_class._member_names_.append(member_name)
        else:
            nonunique = defaultdict(list)
            try:
                try:
                    # try to do a fast lookup to avoid the quadratic loop
                    enum_member = enum_class._value2member_map_[value]
                    if enum_class._unique_:
                        nonunique[enum_member.name].append(member_name)
                except TypeError:
                    # unhashable members are stored elsewhere
                    for unhashable_value, canonical_member in enum_class._value2member_seq_:
                        name = canonical_member.name
                        if unhashable_value == enum_member._value_:
                            if enum_class._unique_:
                                nonunique[name].append(member_name)
                            enum_member = canonical_member
                            break
                    else:
                        raise KeyError
            except KeyError:
                # this could still be an alias if the value is multi-bit and the
                # class is a flag class
                if (
                        Flag is None
                        or not issubclass(enum_class, Flag)
                    ):
                    # no other instances found, record this member in _member_names_
                    enum_class._member_names_.append(member_name)
                elif (
                        Flag is not None
                        and issubclass(enum_class, Flag)
                        and is_single_bit(value)
                    ):
                    # no other instances found, record this member in _member_names_
                    enum_class._member_names_.append(member_name)
            if nonunique:
                # duplicates not allowed if Unique specified
                message = []
                for name, aliases in nonunique.items():
                    bad_aliases = ','.join(aliases)
                    message.append('%s --> %s [%r]' % (name, bad_aliases, enum_class[name].value))
                raise ValueError(
                        '%s: duplicate names found: %s' %
                            (enum_class.__name__, ';  '.join(message))
                        )
        # if self.value is an `auto()`, replace the value attribute with the new enum member
        if isinstance(self.value, auto):
            self.value.enum_member = enum_member
        # if necessary, get redirect in place and then add it to _member_map_
        found_descriptor = None
        descriptor_type = None
        class_type = None
        for base in enum_class.__mro__[1:]:
            attr = base.__dict__.get(member_name)
            if attr is not None:
                if isinstance(attr, (property, DynamicClassAttribute)):
                    found_descriptor = attr
                    class_type = base
                    descriptor_type = 'enum'
                    break
                elif is_descriptor(attr):
                    found_descriptor = attr
                    descriptor_type = descriptor_type or 'desc'
                    class_type = class_type or base
                    continue
                else:
                    descriptor_type = 'attr'
                    class_type = base
        if found_descriptor:
            redirect = property()
            redirect.member = enum_member
            redirect.__set_name__(enum_class, member_name)
            if descriptor_type in ('enum','desc'):
                # earlier descriptor found; copy fget, fset, fdel to this one.
                redirect.fget = getattr(found_descriptor, 'fget', None)
                redirect._get = getattr(found_descriptor, '__get__', None)
                redirect.fset = getattr(found_descriptor, 'fset', None)
                redirect._set = getattr(found_descriptor, '__set__', None)
                redirect.fdel = getattr(found_descriptor, 'fdel', None)
                redirect._del = getattr(found_descriptor, '__delete__', None)
            redirect._attr_type = descriptor_type
            redirect._cls_type = class_type
            setattr(enum_class, member_name, redirect)
        else:
            setattr(enum_class, member_name, enum_member)
        # now add to _member_map_ (even aliases)
        enum_class._member_map_[member_name] = enum_member
        #
        # process (possible) MultiValues
        values = (value, ) + extra_mv_args
        if enum_class._multivalue_ and mv_arg not in values:
            values += (mv_arg, )
        enum_member._values_ = values
        for value in values:
            # first check if value has already been used
            if enum_class._multivalue_ and (
                    value in enum_class._value2member_map_
                    or any(v == value for (v, m) in enum_class._value2member_seq_)
                    ):
                raise ValueError('%r has already been used' % (value, ))
            try:
                # This may fail if value is not hashable. We can't add the value
                # to the map, and by-value lookups for this value will be
                # linear.
                if enum_class._noalias_:
                    raise TypeError('cannot use dict to store value')
                enum_class._value2member_map_[value] = enum_member
            except TypeError:
                enum_class._value2member_seq_ += ((value, enum_member), )

class EnumDict(dict):
    """Track enum member order and ensure member names are not reused.

    EnumType will use the names found in self._member_names as the
    enumeration member names.
    """
    def __init__(self, cls_name, settings, start, constructor_init, constructor_start, constructor_boundary):
        super(EnumDict, self).__init__()
        self._cls_name = cls_name
        self._constructor_init = constructor_init
        self._constructor_start = constructor_start
        self._constructor_boundary = constructor_boundary
        self._generate_next_value = None
        self._member_names = []
        self._member_names_set = set()
        self._settings = settings
        self._addvalue = addvalue = AddValue in settings
        self._magicvalue = MagicValue in settings
        self._multivalue = MultiValue in settings
        if self._addvalue and self._magicvalue:
            raise TypeError('%r: AddValue and MagicValue are mutually exclusive' % cls_name)
        if self._multivalue and self._magicvalue:
            raise TypeError('%r: MultiValue and MagicValue are mutually exclusive' % cls_name)
        self._start = start
        self._addvalue_value = start
        self._new_args = ()
        self._auto_args = False
        # when the magic turns off
        self._locked = MagicValue not in settings
        # if init fields are specified
        self._init = []
        # list of temporary names
        self._ignore = []
        if self._magicvalue:
            self._ignore = ['property', 'staticmethod', 'classmethod']
        self._ignore_init_done = False
        # if _sunder_ values can be changed via the class body
        self._allow_init = True
        self._last_values = []
        self._auto_called = False

    def __getitem__(self, key):
        if key == self._cls_name and self._cls_name not in self:
            return enum
        elif (
                self._locked
                or key in self
                or key in self._ignore
                or is_sunder(key)
                or is_dunder(key)
                ):
            return super(EnumDict, self).__getitem__(key)
        elif self._magicvalue:
            value = self._generate_next_value(key, self._start, len(self._member_names), self._last_values[:])
            self.__setitem__(key, value)
            return value
        else:
            raise Exception('Magic is not set -- why am I here?')

    def __setitem__(self, key, value):
        """Changes anything not sundured, dundered, nor a descriptor.

        If an enum member name is used twice, an error is raised; duplicate
        values are not checked for.

        Single underscore (sunder) names are reserved.
        """
        # Flag classes that have MagicValue and __new__ will get a generated _gnv_
        #
        # if auto() is used in a tuple, auto_store becomes False
        auto_store = True
        if is_internal_class(self._cls_name, value):
            pass
        elif is_private_name(self._cls_name, key):
            pass
        elif is_sunder(key):
            if key not in (
                    '_init_', '_settings_', '_order_', '_ignore_', '_start_',
                    '_create_pseudo_member_', '_create_pseudo_member_values_',
                    '_generate_next_value_', '_boundary_', '_numeric_repr_',
                    '_missing_', '_missing_value_', '_missing_name_',
                    '_iter_member_', '_iter_member_by_value_', '_iter_member_by_def_',
                    ):
                raise ValueError('%r: _sunder_ names, such as %r, are reserved for future Enum use'
                        % (self._cls_name, key)
                        )
            elif not self._allow_init and key not in (
                    'create_pseudo_member_', '_missing_', '_missing_value_', '_missing_name_',
                ):
                # sunder is used during creation, must be specified first
                raise ValueError('%r: cannot set %r after init phase' % (self._cls_name, key))
            elif key == '_ignore_':
                if self._ignore_init_done:
                    raise TypeError('%r: ignore can only be specified once' % self._cls_name)
                if isinstance(value, basestring):
                    value = value.split()
                else:
                    value = list(value)
                self._ignore = value
                already = set(value) & self._member_names_set
                if already:
                    raise ValueError('%r: _ignore_ cannot specify already set names %s' % (
                            self._cls_name,
                            ', '.join(repr(a) for a in already)
                            ))
                self._ignore_init_done = True
            elif key == '_boundary_':
                if self._constructor_boundary:
                    raise TypeError('%r: boundary specified in constructor and class body' % self._cls_name)
            elif key == '_start_':
                if self._constructor_start:
                    raise TypeError('%r: start specified in constructor and class body' % self._cls_name)
                self._start = value
            elif key == '_settings_':
                if not isinstance(value, (set, tuple)):
                    value = (value, )
                if not isinstance(value, set):
                    value = set(value)
                self._settings |= value
                if NoAlias in value and Unique in value:
                    raise TypeError('%r: NoAlias and Unique are mutually exclusive' % self._cls_name)
                elif MultiValue in value and NoAlias in value:
                    raise TypeError('cannot specify both MultiValue and NoAlias' % self._cls_name)
                allowed_settings = dict.fromkeys(['addvalue', 'magicvalue', 'noalias', 'unique', 'multivalue'])
                for arg in self._settings:
                    if arg not in allowed_settings:
                        raise TypeError('%r: unknown qualifier %r (from %r)' % (self._cls_name, arg, value))
                    allowed_settings[arg] = True
                self._multivalue = allowed_settings['multivalue']
                self._addvalue = allowed_settings['addvalue']
                self._magicvalue = allowed_settings['magicvalue']
                self._locked = not self._magicvalue
                if self._magicvalue and not self._ignore_init_done:
                    self._ignore = ['property', 'classmethod', 'staticmethod']
                if self._addvalue and self._init and 'value' not in self._init:
                    self._init.insert(0, 'value')
                value = tuple(self._settings)
            elif key == '_init_':
                if self._constructor_init:
                    raise TypeError('%r: init specified in constructor and in class body' % self._cls_name)
                _init_ = value
                if isinstance(_init_, basestring):
                    _init_ = _init_.replace(',',' ').split()
                if self._addvalue and 'value' not in self._init:
                    self._init.insert(0, 'value')
                if self._magicvalue:
                    raise TypeError("%r: _init_ and MagicValue are mutually exclusive" % self._cls_name)
                self._init = _init_
                value = _init_
            elif key == '_generate_next_value_':
                # check if members already defined as auto()
                if self._auto_called:
                    raise TypeError("_generate_next_value_ must be defined before members")
                gnv = value
                if value is not None:
                    if isinstance(value, staticmethod):
                        gnv = value.__func__
                    elif isinstance(value, classmethod):
                        raise TypeError('%r: _generate_next_value must be a staticmethod, not a classmethod' % self._cls_name)
                    else:
                        gnv = value
                        value = staticmethod(value)
                    self._auto_args = _check_auto_args(value)
                setattr(self, '_generate_next_value', gnv)
        elif is_dunder(key):
            if key == '__order__':
                key = '_order_'
                if not self._allow_init:
                    # _order_ is used during creation, must be specified first
                    raise ValueError('%r: cannot set %r after init phase' % (self._cls_name, key))
            elif key == '__new__':  # and self._new_to_init:
                if isinstance(value, staticmethod):
                    value = value.__func__
                self._new_args = _EnumArgSpec(value)
            elif key == '__init_subclass__':
                if not isinstance(value, classmethod):
                    value = classmethod(value)
            if is_descriptor(value):
                self._locked = True
        elif key in self._member_names_set:
            # descriptor overwriting an enum?
            raise TypeError('%r: attempt to reuse name: %r' % (self._cls_name, key))
        elif key in self._ignore:
            pass
        elif not is_descriptor(value):
            self._allow_init = False
            if key in self:
                # enum overwriting a descriptor?
                raise TypeError('%r: %s already defined as %r' % (self._cls_name, key, self[key]))
            if type(value) is enum:
                value.name = key
                if self._addvalue:
                    raise TypeError('%r: enum() and AddValue are incompatible' % self._cls_name)
            elif self._addvalue and not self._multivalue:
                # generate a value
                value = self._gnv(key, value)
            elif self._multivalue:
                # make sure it's a tuple
                if not type(value) is tuple:
                    value = (value, )
                if isinstance(value[0], auto):
                    value = (self._convert_auto(key, value[0]), ) + value[1:]
                if self._addvalue:
                    value = self._gnv(key, value)
            elif isinstance(value, auto):
                value = self._convert_auto(key, value)
            elif type(value) is tuple and any(isinstance(v, auto) for v in value):
                # insist on an actual tuple, no subclasses, in keeping with only supporting
                # top-level auto() usage (not contained in any other data structure)
                auto_valued = []
                for v in value:
                    if isinstance(v, auto):
                        auto_store = False
                        v = self._convert_auto(key, v)
                        v = v.value
                        self._last_values.append(v)
                    auto_valued.append(v)
                value = tuple(auto_valued)
            elif not isinstance(value, auto):
                # call generate maybe if
                # - init is specified; or
                # - __new__ is specified;
                # and either of them call for more values than are present
                new_args = () or self._new_args and self._new_args.required
                target_len = len(self._init or new_args)
                if isinstance(value, tuple):
                    source_len = len(value)
                else:
                    source_len = 1
                multi_args = len(self._init) > 1 or new_args
                if source_len < target_len :
                    value = self._gnv(key, value)
            else:
                pass
            if self._init:
                if isinstance(value, auto):
                    test_value = value.args
                elif not isinstance(value, tuple):
                    test_value = (value, )
                else:
                    test_value = value
                if len(self._init) != len(test_value):
                    raise TypeError(
                            '%s.%s: number of fields provided do not match init [%r != %r]'
                            % (self._cls_name, key, self._init, test_value)
                            )
            self._member_names.append(key)
            self._member_names_set.add(key)
        else:
            # not a new member, turn off the autoassign magic
            self._locked = True
            self._allow_init = False
        if not (is_sunder(key) or is_dunder(key) or is_private_name(self._cls_name, key) or is_descriptor(value)):
            if not auto_store:
                # reset for next pass
                auto_store = True
            elif isinstance(value, auto):
                self._last_values.append(value.value)
            elif type(value) is tuple:
                if value:
                    if isinstance(value[0], auto):
                        self._last_values.append(value[0].value)
                    else:
                        self._last_values.append(value[0])
            else:
                self._last_values.append(value)
        super(EnumDict, self).__setitem__(key, value)

    def _convert_auto(self, key, value):
        # if auto.args or auto.kwds, compare to _init_ and __new__ -- if lacking, call gnv
        # if not auto.args|kwds but auto.value is _auto_null -- call gnv
        if value.args or value.kwds or value.value is _auto_null:
            if value.args or value.kwds:
                values = value.args
            else:
                values = ()
            new_args = () or self._new_args and self._new_args.required
            target_len = len(self._init or new_args) or 1
            if type(values) is tuple:
                source_len = len(values)
            else:
                source_len = 1
            multi_args = len(self._init) > 1 or new_args
            if source_len < target_len :
                values = self._gnv(key, values)
                self._auto_called = True
                if value.args:
                    value._args = values
                else:
                    value.value = values
        return value

    def _gnv(self, key, value):
        # generate a value
        if self._auto_args:
            if not isinstance(value, tuple):
                value = (value, )
            value = self._generate_next_value(key, self._start, len(self._member_names), self._last_values[:], *value)
        else:
            value = self._generate_next_value(key, self._start, len(self._member_names), self._last_values[:])
        if isinstance(value, tuple) and len(value) == 1:
            value = value[0]
        return value


no_arg = SentinelType('no_arg', (type, ), {})
class EnumType(type):
    """Metaclass for Enum"""

    @classmethod
    def __prepare__(metacls, cls, bases, init=None, start=None, settings=(), boundary=None, **kwds):
        metacls._check_for_existing_members_(cls, bases)
        if Flag is None and cls == 'Flag':
            initial_flag = True
        else:
            initial_flag = False
        # settings are a combination of current and all past settings
        constructor_init = init is not None
        constructor_start = start is not None
        constructor_boundary = boundary is not None
        if not isinstance(settings, tuple):
            settings = settings,
        settings = set(settings)
        generate = None
        order = None
        # inherit previous flags
        member_type, first_enum = metacls._get_mixins_(cls, bases)
        if first_enum is not None:
            generate = getattr(first_enum, '_generate_next_value_', None)
            generate = getattr(generate, 'im_func', generate)
            settings |= metacls._get_settings_(bases)
            init = init or first_enum._auto_init_[:]
            order = first_enum._order_function_
            if start is None:
                start = first_enum._start_
        else:
            # first time through -- creating Enum itself
            start = 1
        # check for custom settings
        if AddValue in settings and init and 'value' not in init:
            if isinstance(init, list):
                init.insert(0, 'value')
            else:
                init = 'value ' + init
        if NoAlias in settings and Unique in settings:
            raise TypeError('%r: NoAlias and Unique are mutually exclusive' % cls)
        if MultiValue in settings and NoAlias in settings:
            raise TypeError('%r: MultiValue and NoAlias are mutually exclusive' % cls)
        allowed_settings = dict.fromkeys(['addvalue', 'magicvalue', 'noalias', 'unique', 'multivalue'])
        for arg in settings:
            if arg not in allowed_settings:
                raise TypeError('%r: unknown qualifier %r' % (cls, arg))
        enum_dict = EnumDict(cls_name=cls, settings=settings, start=start, constructor_init=constructor_init, constructor_start=constructor_start, constructor_boundary=constructor_boundary)
        enum_dict._member_type = member_type
        enum_dict._base_type = ('enum', 'flag')[
                Flag is None and cls == 'Flag'
                or
                Flag is not None and any(issubclass(b, Flag) for b in bases)
                ]
        if Flag is not None and any(b is Flag for b in bases) and member_type not in (baseinteger + (object, )):
            if Flag in bases:
                # when a non-int data type is mixed in with Flag, we end up
                # needing two values for two `__new__`s:
                # - the integer value for the Flag itself; and
                # - the mix-in value for the mix-in
                #
                # we provide a default `_generate_next_value_` to supply the int
                # argument, and a default `__new__` to keep the two straight
                def _generate_next_value_(name, start, count, values, *args, **kwds):
                    return (2 ** count, ) + args
                enum_dict['_generate_next_value_'] = staticmethod(_generate_next_value_)
                def __new__(cls, flag_value, type_value):
                    obj = member_type.__new__(cls, type_value)
                    obj._value_ = flag_value
                    return obj
                enum_dict['__new__'] = __new__
            else:
                try:
                    enum_dict._new_args = _EnumArgSpec(first_enum.__new_member__)
                except TypeError:
                    pass
        elif not initial_flag:
            if hasattr(first_enum, '__new_member__'):
                enum_dict._new_args = _EnumArgSpec(first_enum.__new_member__)
            if generate:
                enum_dict['_generate_next_value_'] = generate
                enum_dict._inherited_gnv = True
            if init is not None:
                if isinstance(init, basestring):
                    init = init.replace(',',' ').split()
                enum_dict._init = init
        elif hasattr(first_enum, '__new_member__'):
            enum_dict._new_args = _EnumArgSpec(first_enum.__new_member__)
        if order is not None:
            enum_dict['_order_'] = staticmethod(order)
        return enum_dict

    def __init__(cls, *args , **kwds):
        pass

    def __new__(metacls, cls, bases, clsdict, init=None, start=None, settings=(), boundary=None, **kwds):
        # handle py2 case first
        if type(clsdict) is not EnumDict:
            # py2 and/or functional API gyrations
            init = clsdict.pop('_init_', None)
            start = clsdict.pop('_start_', None)
            settings = clsdict.pop('_settings_', ())
            _order_ = clsdict.pop('_order_', clsdict.pop('__order__', None))
            _ignore_ = clsdict.pop('_ignore_', None)
            _create_pseudo_member_ = clsdict.pop('_create_pseudo_member_', None)
            _create_pseudo_member_values_ = clsdict.pop('_create_pseudo_member_values_', None)
            _generate_next_value_ = clsdict.pop('_generate_next_value_', None)
            _missing_ = clsdict.pop('_missing_', None)
            _missing_value_ = clsdict.pop('_missing_value_', None)
            _missing_name_ = clsdict.pop('_missing_name_', None)
            _boundary_ = clsdict.pop('_boundary_', None)
            _iter_member_ = clsdict.pop('_iter_member_', None)
            _iter_member_by_value_ = clsdict.pop('_iter_member_by_value_', None)
            _iter_member_by_def_ = clsdict.pop('_iter_member_by_def_', None)
            __new__ = clsdict.pop('__new__', None)
            __new__ = getattr(__new__, 'im_func', __new__)
            __new__ = getattr(__new__, '__func__', __new__)
            enum_members = dict([
                    (k, v) for (k, v) in clsdict.items()
                    if not (is_sunder(k) or is_dunder(k) or is_private_name(cls, k) or is_descriptor(v))
                    ])
            original_dict = clsdict
            clsdict = metacls.__prepare__(cls, bases, init=init, start=start)
            if settings:
                clsdict['_settings_'] = settings
            init = init or clsdict._init
            if _order_ is None:
                _order_ = clsdict.get('_order_')
                if _order_ is not None:
                    _order_ = _order_.__get__(cls)
            if isinstance(original_dict, OrderedDict):
                calced_order = original_dict
            elif _order_ is None:
                calced_order = [name for (name, value) in enumsort(list(enum_members.items()))]
            elif isinstance(_order_, basestring):
                calced_order = _order_ = _order_.replace(',', ' ').split()
            elif callable(_order_):
                if init:
                    if not isinstance(init, basestring):
                        init = ' '.join(init)
                member = NamedTuple('member', init and 'name ' + init or ['name', 'value'])
                calced_order = []
                for name, value in enum_members.items():
                    if init:
                        if not isinstance(value, tuple):
                            value = (value, )
                        name_value = (name, ) + value
                    else:
                        name_value = tuple((name, value))
                    if member._defined_len_ != len(name_value):
                        raise TypeError('%d values expected (%s), %d received (%s)' % (
                            member._defined_len_,
                            ', '.join(member._fields_),
                            len(name_value),
                            ', '.join([repr(v) for v in name_value]),
                            ))
                    calced_order.append(member(*name_value))
                calced_order = [m.name for m in sorted(calced_order, key=_order_)]
            else:
                calced_order = _order_
            for name in (
                    '_missing_', '_missing_value_', '_missing_name_',
                    '_ignore_', '_create_pseudo_member_', '_create_pseudo_member_values_',
                    '_generate_next_value_', '_order_', '__new__',
                    '_missing_', '_missing_value_', '_missing_name_',
                    '_boundary_',
                    '_iter_member_', '_iter_member_by_value_', '_iter_member_by_def_',
                ):
                attr = locals()[name]
                if attr is not None:
                    clsdict[name] = attr
            # now add members
            for k in calced_order:
                try:
                    clsdict[k] = original_dict[k]
                except KeyError:
                    # this error will be handled when _order_ is checked
                    pass
            for k, v in original_dict.items():
                if k not in calced_order:
                    clsdict[k] = v
            del _order_, _ignore_, _create_pseudo_member_, _create_pseudo_member_values_,
            del _generate_next_value_, _missing_, _missing_value_, _missing_name_
        #
        # resume normal path
        clsdict._locked = True
        #
        # check for illegal enum names (any others?)
        member_names = clsdict._member_names
        invalid_names = set(member_names) & set(['mro', ''])
        if invalid_names:
            raise ValueError('invalid enum member name(s): %s' % (
                ', '.join(invalid_names), ))
        _order_ = clsdict.pop('_order_', None)
        if isinstance(_order_, basestring):
            _order_ = _order_.replace(',',' ').split()
        init = clsdict._init
        start = clsdict._start
        settings = clsdict._settings
        creating_init = []
        new_args = clsdict._new_args
        auto_args = clsdict._auto_args
        auto_init = False
        if init is not None:
            auto_init = True
            creating_init = init[:]
        if 'value' in creating_init and creating_init[0] != 'value':
            raise TypeError("'value', if specified, must be the first item in 'init'")
        magicvalue = MagicValue in settings
        multivalue = MultiValue in settings
        noalias = NoAlias in settings
        unique = Unique in settings
        # an Enum class cannot be mixed with other types (int, float, etc.) if
        #   it has an inherited __new__ unless a new __new__ is defined (or
        #   the resulting class will fail).
        # an Enum class is final once enumeration items have been defined;
        #
        # remove any keys listed in _ignore_
        clsdict.setdefault('_ignore_', []).append('_ignore_')
        ignore = clsdict['_ignore_']
        for key in ignore:
            clsdict.pop(key, None)
        #
        boundary = boundary or clsdict.pop('_boundary_', None)
        _gnv = clsdict.get('_generate_next_value_')
        if _gnv is not None and type(_gnv) is not staticmethod:
            _gnv = staticmethod(_gnv)
        # convert to regular dict
        clsdict = dict(clsdict.items())
        if _gnv is not None:
            clsdict['_generate_next_value_'] = _gnv
        member_type, first_enum = metacls._get_mixins_(cls, bases)
        # get the method to create enum members
        __new__, save_new, new_uses_args = metacls._find_new_(
                clsdict,
                member_type,
                first_enum,
                )
        clsdict['_new_member_'] = staticmethod(__new__)
        clsdict['_use_args_'] = new_uses_args
        #
        # convert future enum members into temporary _proto_members
        for name in member_names:
            value = clsdict[name]
            clsdict[name] = _proto_member(value)
        #
        # temp stuff
        clsdict['_creating_init_'] = creating_init
        clsdict['_multivalue_'] = multivalue
        clsdict['_magicvalue_'] = magicvalue
        clsdict['_noalias_'] = noalias
        clsdict['_unique_'] = unique
        #
        # house-keeping structures
        clsdict['_member_names_'] = []
        clsdict['_member_map_'] = OrderedDict()
        clsdict['_member_type_'] = member_type
        clsdict['_value2member_map_'] = {}
        clsdict['_value2member_seq_'] = ()
        clsdict['_settings_'] = settings
        clsdict['_start_'] = start
        clsdict['_auto_init_'] = init
        clsdict['_new_args_'] = new_args
        clsdict['_auto_args_'] = auto_args
        clsdict['_order_function_'] = None
        # now set the __repr__ for the value
        clsdict['_value_repr_'] = metacls._find_data_repr_(cls, bases)
        #
        # Flag structures (will be removed if final class is not a Flag
        clsdict['_boundary_'] = (
                boundary
                or getattr(first_enum, '_boundary_', None)
                )
        clsdict['_flag_mask_'] = 0
        clsdict['_singles_mask_'] = 0
        clsdict['_all_bits_'] = 0
        clsdict['_inverted_'] = None
        #
        # move skipped values out of the descriptor
        for name, obj in clsdict.items():
            if isinstance(obj, nonmember):
                clsdict[name] = obj.value
        #
        # If a custom type is mixed into the Enum, and it does not know how
        # to pickle itself, pickle.dumps will succeed but pickle.loads will
        # fail.  Rather than have the error show up later and possibly far
        # from the source, sabotage the pickle protocol for this class so
        # that pickle.dumps also fails.
        #
        # However, if the new class implements its own __reduce_ex__, do not
        # sabotage -- it's on them to make sure it works correctly.  We use
        # __reduce_ex__ instead of any of the others as it is preferred by
        # pickle over __reduce__, and it handles all pickle protocols.
        unpicklable = False
        if '__reduce_ex__' not in clsdict:
            if member_type is not object:
                methods = ('__getnewargs_ex__', '__getnewargs__',
                        '__reduce_ex__', '__reduce__')
                if not any(m in member_type.__dict__ for m in methods):
                    make_class_unpicklable(clsdict)
                    unpicklable = True
        #
        # create a default docstring if one has not been provided
        if '__doc__' not in clsdict:
            clsdict['__doc__'] = 'An enumeration.'
        #
        # create our new Enum type
        try:
            exc = None
            enum_class = type.__new__(metacls, cls, bases, clsdict)
        except RuntimeError as e:
            # any exceptions raised by _proto_member (aka member.__new__) will get converted to
            # a RuntimeError, so get that original exception back and raise
            # it instead
            exc = e.__cause__ or e
        if exc is not None:
            raise exc
        #
        # if Python 3.5 or ealier, implement the __set_name__ and
        # __init_subclass__ protocols
        if pyver < PY3_6:
            for name in member_names:
                enum_class.__dict__[name].__set_name__(enum_class, name)
            for name, obj in enum_class.__dict__.items():
                if name in member_names:
                    continue
                if hasattr(obj, '__set_name__'):
                    obj.__set_name__(enum_class, name)
            if Enum is not None and hasattr(enum_class, '__init_subclass__'):
                super(enum_class, enum_class).__init_subclass__()
        #
        # double check that repr and friends are not the mixin's or various
        # things break (such as pickle)
        #
        # Also, special handling for ReprEnum
        if ReprEnum is not None and ReprEnum in bases:
            if member_type is object:
                raise TypeError(
                        'ReprEnum subclasses must be mixed with a data type (i.e.'
                        ' int, str, float, etc.)'
                        )
            if '__format__' not in clsdict:
                enum_class.__format__ = member_type.__format__
                clsdict['__format__'] = enum_class.__format__
            if '__str__' not in clsdict:
                method = member_type.__str__
                if method is object.__str__:
                    # if member_type does not define __str__, object.__str__ will use
                    # its __repr__ instead, so we'll also use its __repr__
                    method = member_type.__repr__
                enum_class.__str__ = method
                clsdict['__str__'] = enum_class.__str__

        for name in ('__repr__', '__str__', '__format__', '__reduce_ex__'):
            if name in clsdict:
                # class has defined/imported/copied the method
                continue
            class_method = getattr(enum_class, name)
            obj_method = getattr(member_type, name, None)
            enum_method = getattr(first_enum, name, None)
            if obj_method is not None and obj_method == class_method:
                if name == '__reduce_ex__' and unpicklable:
                    continue
                setattr(enum_class, name, enum_method)
                clsdict[name] = enum_method
        #
        # for Flag, add __or__, __and__, __xor__, and __invert__
        if Flag is not None and issubclass(enum_class, Flag):
            for name in (
                    '__or__', '__and__', '__xor__',
                    '__ror__', '__rand__', '__rxor__',
                    '__invert__'
                ):
                if name not in clsdict:
                    setattr(enum_class, name, getattr(Flag, name))
                    clsdict[name] = enum_method
        #
        # method resolution and int's are not playing nice
        # Python's less than 2.6 use __cmp__
        if pyver < PY2_6:
            #
            if issubclass(enum_class, int):
                setattr(enum_class, '__cmp__', getattr(int, '__cmp__'))
            #
        elif PY2:
            #
            if issubclass(enum_class, int):
                for method in (
                        '__le__',
                        '__lt__',
                        '__gt__',
                        '__ge__',
                        '__eq__',
                        '__ne__',
                        '__hash__',
                        ):
                    setattr(enum_class, method, getattr(int, method))
        #
        # replace any other __new__ with our own (as long as Enum is not None,
        # anyway) -- again, this is to support pickle
        if Enum is not None:
            # if the user defined their own __new__, save it before it gets
            # clobbered in case they subclass later
            if save_new:
                setattr(enum_class, '__new_member__', enum_class.__dict__['__new__'])
            setattr(enum_class, '__new__', Enum.__dict__['__new__'])
        #
        # _order_ checking is spread out into three/four steps
        # - ensure _order_ is a list, not a string nor a function
        # - if enum_class is a Flag:
        #   - remove any non-single-bit flags from _order_
        # - remove any aliases from _order_
        # - check that _order_ and _member_names_ match
        #
        # _order_ step 1: ensure _order_ is a list
        if _order_:
            if isinstance(_order_, staticmethod):
                _order_ = _order_.__func__
            if callable(_order_):
                # save order for future subclasses
                enum_class._order_function_ = staticmethod(_order_)
                # create ordered list for comparison
                _order_ = [m.name for m in sorted(enum_class, key=_order_)]
        #
        # remove Flag structures if final class is not a Flag
        if (
                Flag is None and cls != 'Flag'
                or Flag is not None and not issubclass(enum_class, Flag)
            ):
            delattr(enum_class, '_boundary_')
            delattr(enum_class, '_flag_mask_')
            delattr(enum_class, '_singles_mask_')
            delattr(enum_class, '_all_bits_')
            delattr(enum_class, '_inverted_')
        elif Flag is not None and issubclass(enum_class, Flag):
            # set correct __iter__
            if [m._value_ for m in enum_class] != sorted([m._value_ for m in enum_class]):
                enum_class._iter_member_ = enum_class._iter_member_by_def_
            if _order_:
                # _order_ step 2: remove any items from _order_ that are not single-bit
                _order_ = [
                        o
                        for o in _order_
                        if o not in enum_class._member_map_ or is_single_bit(enum_class[o]._value_)
                        ]
        #
        # check for constants with auto() values
        for k, v in enum_class.__dict__.items():
            if isinstance(v, constant) and isinstance(v.value, auto):
                v.value = enum_class(v.value.value)
        #
        if _order_:
            # _order_ step 3: remove aliases from _order_
            _order_ = [
                    o
                    for o in _order_
                    if (
                        o not in enum_class._member_map_
                        or
                        (o in enum_class._member_map_ and o in enum_class._member_names_)
                        )]
            # _order_ step 4: verify that _order_ and _member_names_ match
            if _order_ != enum_class._member_names_:
                raise TypeError(
                        'member order does not match _order_:\n%r\n%r'
                        % (enum_class._member_names_, _order_)
                        )
        return enum_class

    def __bool__(cls):
        """
        classes/types should always be True.
        """
        return True

    def __call__(cls, value=no_arg, names=None, module=None, qualname=None, type=None, start=1, boundary=None):
        """Either returns an existing member, or creates a new enum class.

        This method is used both when an enum class is given a value to match
        to an enumeration member (i.e. Color(3)) and for the functional API
        (i.e. Color = Enum('Color', names='red green blue')).

        When used for the functional API: `module`, if set, will be stored in
        the new class' __module__ attribute; `type`, if set, will be mixed in
        as the first base class.

        Note: if `module` is not set this routine will attempt to discover the
        calling module by walking the frame stack; if this is unsuccessful
        the resulting class will not be pickleable.
        """
        if names is None:  # simple value lookup
            return cls.__new__(cls, value)
        # otherwise, functional API: we're creating a new Enum type
        return cls._create_(value, names, module=module, qualname=qualname, type=type, start=start, boundary=boundary)

    def __contains__(cls, value):
        """Return True if `value` is in `cls`.

        `value` is in `cls` if:
        1) `value` is a member of `cls`, or
        2) `value` is the value of one of the `cls`'s members.
        """
        if isinstance(value, cls):
            return True
        try:
            return value in cls._value2member_map_
        except TypeError:
            return value in [v for v,m in cls._value2member_seq_]

    def __delattr__(cls, attr):
        # nicer error message when someone tries to delete an attribute
        # (see issue19025).
        if attr in cls._member_map_:
            raise AttributeError(
                    "%s: cannot delete Enum member %r." % (cls.__name__, attr),
                    )
        found_attr = get_attr_from_chain(cls, attr)
        if isinstance(found_attr, constant):
            raise AttributeError(
                    "%s: cannot delete constant %r" % (cls.__name__, attr),
                    )
        elif isinstance(found_attr, property):
            raise AttributeError(
                    "%s: cannot delete property %r" % (cls.__name__, attr),
                    )
        type.__delattr__(cls, attr)

    def __dir__(cls):
        interesting = set(cls._member_names_ + [
                    '__class__', '__contains__', '__doc__', '__getitem__',
                    '__iter__', '__len__', '__members__', '__module__',
                    '__name__',
                    ])
        if cls._new_member_ is not object.__new__:
            interesting.add('__new__')
        if cls.__init_subclass__ is not Enum.__init_subclass__:
            interesting.add('__init_subclass__')
        if hasattr(object, '__qualname__'):
            interesting.add('__qualname__')
        for method in ('__init__', '__format__', '__repr__', '__str__'):
            if getattr(cls, method) not in (getattr(Enum, method), getattr(Flag, method)):
                interesting.add(method)
        if cls._member_type_ is object:
            return sorted(interesting)
        else:
            # return whatever mixed-in data type has
            return sorted(set(dir(cls._member_type_)) | interesting)

    @bltin_property
    def __members__(cls):
        """Returns a mapping of member name->value.

        This mapping lists all enum members, including aliases. Note that this
        is a copy of the internal mapping.
        """
        return cls._member_map_.copy()

    def __getitem__(cls, name):
        try:
            return cls._member_map_[name]
        except KeyError:
            exc = _sys.exc_info()[1]
        if Flag is not None and issubclass(cls, Flag) and '|' in name:
            try:
                # may be an __or__ed name
                result = cls(0)
                for n in name.split('|'):
                    result |= cls[n]
                return result
            except KeyError:
                raise exc
        result = cls._missing_name_(name)
        if isinstance(result, cls):
            return result
        else:
            raise exc

    def __iter__(cls):
        return (cls._member_map_[name] for name in cls._member_names_)

    def __reversed__(cls):
        return (cls._member_map_[name] for name in reversed(cls._member_names_))

    def __len__(cls):
        return len(cls._member_names_)

    __nonzero__ = __bool__

    def __repr__(cls):
        return "<aenum %r>" % (cls.__name__, )

    def __setattr__(cls, name, value):
        """Block attempts to reassign Enum members/constants.

        A simple assignment to the class namespace only changes one of the
        several possible ways to get an Enum member from the Enum class,
        resulting in an inconsistent Enumeration.
        """
        member_map = cls.__dict__.get('_member_map_', {})
        if name in member_map:
            raise AttributeError(
                    '%s: cannot rebind member %r.' % (cls.__name__, name),
                    )
        found_attr = get_attr_from_chain(cls, name)
        if isinstance(found_attr, constant):
            raise AttributeError(
                    "%s: cannot rebind constant %r" % (cls.__name__, name),
                    )
        elif isinstance(found_attr, (bltin_property, property)) and not isinstance(value, property):
            raise AttributeError(
                    "%s: cannot rebind property %r" % (cls.__name__, name),
                    )
        type.__setattr__(cls, name, value)

    def _convert(cls, *args, **kwds):
        import warnings
        warnings.warn("_convert is deprecated and will be removed, use"
                      " _convert_ instead.", DeprecationWarning, stacklevel=2)
        return cls._convert_(*args, **kwds)

    def _convert_(cls, name, module, filter, source=None, boundary=None, as_global=False):
        """
        Create a new Enum subclass that replaces a collection of global constants
        """
        # convert all constants from source (or module) that pass filter() to
        # a new Enum called name, and export the enum and its members back to
        # module;
        # also, replace the __reduce_ex__ method so unpickling works in
        # previous Python versions
        module_globals = vars(_sys.modules[module])
        if source:
            source = vars(source)
        else:
            source = module_globals
        members = [(key, source[key]) for key in source.keys() if filter(key)]
        try:
            # sort by value, name
            members.sort(key=lambda t: (t[1], t[0]))
        except TypeError:
            # unless some values aren't comparable, in which case sort by just name
            members.sort(key=lambda t: t[0])
        cls = cls(name, members, module=module, boundary=boundary or KEEP)
        cls.__reduce_ex__ = _reduce_ex_by_name
        if as_global:
            global_enum(cls)
        else:
            module_globals.update(cls.__members__)
        module_globals[name] = cls
        return cls

    def _create_(cls, class_name, names, module=None, qualname=None, type=None, start=1, boundary=None):
        """Convenience method to create a new Enum class.

        `names` can be:

        * A string containing member names, separated either with spaces or
          commas.  Values are auto-numbered from 1.
        * An iterable of member names.  Values are auto-numbered from 1.
        * An iterable of (member name, value) pairs.
        * A mapping of member name -> value.
        """
        if PY2:
            # if class_name is unicode, attempt a conversion to ASCII
            if isinstance(class_name, unicode):
                try:
                    class_name = class_name.encode('ascii')
                except UnicodeEncodeError:
                    raise TypeError('%r is not representable in ASCII' % (class_name, ))
        metacls = cls.__class__
        if type is None:
            bases = (cls, )
        else:
            bases = (type, cls)
        _, first_enum = cls._get_mixins_(class_name, bases)
        generate = getattr(first_enum, '_generate_next_value_', None)
        generate = getattr(generate, 'im_func', generate)
        # special processing needed for names?
        if isinstance(names, basestring):
            names = names.replace(',', ' ').split()
        if isinstance(names, (tuple, list)) and names and isinstance(names[0], basestring):
            original_names, names = names, []
            last_values = []
            for count, name in enumerate(original_names):
                value = generate(name, start, count, last_values[:])
                last_values.append(value)
                names.append((name, value))
        # Here, names is either an iterable of (name, value) or a mapping.
        item = None  # in case names is empty
        clsdict = None
        for item in names:
            if clsdict is None:
                # first time initialization
                if isinstance(item, basestring):
                    clsdict = {}
                else:
                    # remember the order
                    clsdict = metacls.__prepare__(class_name, bases)
            if isinstance(item, basestring):
                member_name, member_value = item, names[item]
            else:
                member_name, member_value = item
            clsdict[member_name] = member_value
        if clsdict is None:
            # in case names was empty
            clsdict = metacls.__prepare__(class_name, bases)
        enum_class = metacls.__new__(metacls, class_name, bases, clsdict, boundary=boundary)
        # TODO: replace the frame hack if a blessed way to know the calling
        # module is ever developed
        if module is None:
            try:
                module = _sys._getframe(2).f_globals['__name__']
            except (AttributeError, KeyError):
                pass
        if module is None:
            make_class_unpicklable(enum_class)
        else:
            enum_class.__module__ = module
        if qualname is not None:
            enum_class.__qualname__ = qualname
        return enum_class

    @classmethod
    def _check_for_existing_members_(mcls, class_name, bases):
        if Enum is None:
            return
        for chain in bases:
            for base in chain.__mro__:
                if issubclass(base, Enum) and base._member_names_:
                    raise TypeError(
                            "<aenum %r> cannot extend %r"
                            % (class_name, base)
                            )
    @classmethod
    def _get_mixins_(mcls, class_name, bases):
        """Returns the type for creating enum members, and the first inherited
        enum class.

        bases: the tuple of bases that was given to __new__
        """
        if not bases or Enum is None:
            return object, Enum

        mcls._check_for_existing_members_(class_name, bases)

        # ensure final parent class is an Enum derivative, find any concrete
        # data type, and check that Enum has no members
        first_enum = bases[-1]
        if first_enum in stdlib_enums:
            first_enum = bases[-2]
        if not issubclass(first_enum, Enum):
            raise TypeError("new enumerations should be created as "
                    "`EnumName([mixin_type, ...] [data_type,] enum_type)`")
        member_type = mcls._find_data_type_(class_name, bases) or object
        if first_enum._member_names_:
            raise TypeError("cannot extend enumerations via subclassing")
        #
        return member_type, first_enum

    @classmethod
    def _find_data_repr_(mcls, class_name, bases):
        for chain in bases:
            for base in chain.__mro__:
                if base in ((object, ) + stdlib_enums):
                    continue
                elif isinstance(base, EnumType):
                    # if we hit an Enum, use it's _value_repr_
                    return base._value_repr_
                elif '__repr__' in base.__dict__:
                    # this is our data repr
                    # double-check if a dataclass with a default __repr__
                    if (
                            '__dataclass_fields__' in base.__dict__
                            and '__dataclass_params__' in base.__dict__
                            and base.__dict__['__dataclass_params__'].repr
                        ):
                        return _dataclass_repr
                    else:
                        return base.__dict__['__repr__']
        return None

    @classmethod
    def _find_data_type_(mcls, class_name, bases):
        data_types = set()
        for chain in bases:
            candidate = None
            for base in chain.__mro__:
                if base in ((object, ) + stdlib_enums):
                    continue
                elif isinstance(base, EnumType):
                    if base._member_type_ is not object:
                        data_types.add(base._member_type_)
                        break
                elif '__new__' in base.__dict__ or '__dataclass_fields__' in base.__dict__:
                    if isinstance(base, EnumType):
                        continue
                    elif StdlibFlag is not None and issubclass(base, StdlibFlag):
                        continue
                    data_types.add(candidate or base)
                    break
                else:
                    candidate = candidate or base
        if len(data_types) > 1:
            raise TypeError('%r: too many data types: %r' % (class_name, data_types))
        elif data_types:
            return data_types.pop()
        else:
            return None

    @staticmethod
    def _get_settings_(bases):
        """Returns the combined _settings_ of all Enum base classes

        bases: the tuple of bases given to __new__
        """
        settings = set()
        for chain in bases:
            for base in chain.__mro__:
                if issubclass(base, Enum):
                    for s in base._settings_:
                        settings.add(s)
        return settings

    @classmethod
    def _find_new_(mcls, clsdict, member_type, first_enum):
        """Returns the __new__ to be used for creating the enum members.

        clsdict: the class dictionary given to __new__
        member_type: the data type whose __new__ will be used by default
        first_enum: enumeration to check for an overriding __new__
        """
        # now find the correct __new__, checking to see of one was defined
        # by the user; also check earlier enum classes in case a __new__ was
        # saved as __new_member__
        __new__ = clsdict.get('__new__', None)
        #
        # should __new__ be saved as __new_member__ later?
        save_new = first_enum is not None and __new__ is not None
        #
        if __new__ is None:
            # check all possibles for __new_member__ before falling back to
            # __new__
            for method in ('__new_member__', '__new__'):
                for possible in (member_type, first_enum):
                    target = getattr(possible, method, None)
                    if target not in (
                            None,
                            None.__new__,
                            object.__new__,
                            Enum.__new__,
                            StdlibEnum.__new__,
                            ):
                        __new__ = target
                        break
                if __new__ is not None:
                    break
            else:
                __new__ = object.__new__
        # if a non-object.__new__ is used then whatever value/tuple was
        # assigned to the enum member name will be passed to __new__ and to the
        # new enum member's __init__
        if first_enum is None or __new__ in (Enum.__new__, object.__new__):
            new_uses_args = False
        else:
            new_uses_args = True
        #
        return __new__, save_new, new_uses_args


    # In order to support Python 2 and 3 with a single
    # codebase we have to create the Enum methods separately
    # and then use the `type(name, bases, dict)` method to
    # create the class.

if StdlibEnumMeta:
    class EnumType(EnumType, StdlibEnumMeta):
        pass
EnumMeta = EnumType

enum_dict = _Addendum(
        dict=EnumType.__prepare__('Enum', (object, )),
        doc="Generic enumeration.\n\n    Derive from this class to define new enumerations.\n\n",
        ns=globals(),
        )

@enum_dict
@classmethod
def __signature__(cls):
    if cls._member_names_:
        return '(*values)'
    else:
        return '(new_class_name, /, names, *, module=None, qualname=None, type=None, start=1, boundary=None)'

@enum_dict
def __init__(self, *args, **kwds):
    # auto-init method
    _auto_init_ = self._auto_init_
    if _auto_init_ is None:
        return
    if 'value' in _auto_init_:
        # remove 'value' from _auto_init_ as it has already been handled
        _auto_init_ = _auto_init_[1:]
    if _auto_init_:
        if len(_auto_init_) < len(args):
            raise TypeError('%d arguments expected (%s), %d received (%s)'
                    % (len(_auto_init_), _auto_init_, len(args), args))
        for name, arg in zip(_auto_init_, args):
            setattr(self, name, arg)
        if len(args) < len(_auto_init_):
            remaining_args = _auto_init_[len(args):]
            for name in remaining_args:
                value = kwds.pop(name, undefined)
                if value is undefined:
                    raise TypeError('missing value for: %r' % (name, ))
                setattr(self, name, value)
            if kwds:
                # too many keyword arguments
                raise TypeError('invalid keyword(s): %s' % ', '.join(kwds.keys()))

@enum_dict
def __new__(cls, value):
    # all enum instances are actually created during class construction
    # without calling this method; this method is called by the metaclass'
    # __call__ (i.e. Color(3) ), and by pickle
    if NoAlias in cls._settings_:
        raise TypeError('NoAlias enumerations cannot be looked up by value')
    if type(value) is cls:
        # For lookups like Color(Color.red)
        # value = value.value
        return value
    # by-value search for a matching enum member
    # see if it's in the reverse mapping (for hashable values)
    try:
        return cls._value2member_map_[value]
    except KeyError:
        # Not found, no need to do long O(n) search
        pass
    except TypeError:
        # not there, now do long search -- O(n) behavior
        for member_value, member in cls._value2member_seq_:
            if member_value == value:
                return member
    # still not found -- try _missing_ hook
    result = cls._missing_value_(value)
    if isinstance(result, cls):
        return result
    elif result is not None and getattr(cls, '_boundary_', None) is EJECT:
        return result
    else:
        if result is None:
            if value is no_arg:
                raise ValueError('%s() should be called with a value' % (cls.__name__, ))
            else:
                raise ValueError("%r is not a valid %s" % (value, cls.__name__))
        else:
            raise TypeError(
                    'error in %s._missing_: returned %r instead of None or a valid member'
                    % (cls.__name__, result)
                    )

@enum_dict
@classmethod
def __init_subclass__(cls, **kwds):
    if pyver < PY3_6:
        # end of the line
        if kwds:
            raise TypeError('unconsumed keyword arguments: %r' % (kwds, ))
    else:
        super(Enum, cls).__init_subclass__(**kwds)

@enum_dict
@staticmethod
def _generate_next_value_(name, start, count, last_values, *args, **kwds):
    for last_value in reversed(last_values):
        try:
            new_value = last_value + 1
            break
        except TypeError:
            pass
    else:
        new_value = start
    if args:
        return (new_value, ) + args
    else:
        return new_value

@enum_dict
@classmethod
def _missing_(cls, value):
    "deprecated, use _missing_value_ instead"
    return None

@enum_dict
@classmethod
def _missing_value_(cls, value):
    "used for failed value access"
    return cls._missing_(value)

@enum_dict
@classmethod
def _missing_name_(cls, name):
    "used for failed item access"
    return None

@enum_dict
def __repr__(self):
    v_repr = self.__class__._value_repr_ or self._value_.__class__.__repr__
    return "<%s.%s: %s>" % (self.__class__.__name__, self._name_, v_repr(self._value_))

@enum_dict
def __str__(self):
    return "%s.%s" % (self.__class__.__name__, self._name_)

if PY3:
    @enum_dict
    def __dir__(self):
        """
        Returns all members and all public methods
        """
        if self.__class__._member_type_ is object:
            interesting = set(['__class__', '__doc__', '__eq__', '__hash__', '__module__'])
        else:
            interesting = set(n for n in object.__dir__(self) if n not in self._member_map_)
        for name in getattr(self, '__dict__', []):
            if name[0] != '_':
                interesting.add(name)
        for cls in self.__class__.mro():
            for name, obj in cls.__dict__.items():
                if name[0] == '_':
                    continue
                if isinstance(obj, property):
                    # that's an enum.property
                    if obj.fget is not None or name not in self._member_map_:
                        interesting.add(name)
                    else:
                        # in case it was added by `dir(self)`
                        interesting.discard(name)
                elif not isinstance(obj, self.__class__):
                    interesting.add(name)
        return sorted(interesting)

@enum_dict
def __format__(self, format_spec):
    return str.__format__(str(self), format_spec)

@enum_dict
def __hash__(self):
    return hash(self._name_)

@enum_dict
def __reduce_ex__(self, proto):
    return self.__class__, (self._value_, )

@enum_dict
def __le__(self, other):
    raise TypeError("unorderable types: %s() <= %s()" % (self.__class__.__name__, other.__class__.__name__))

@enum_dict
def __lt__(self, other):
    raise TypeError("unorderable types: %s() < %s()" % (self.__class__.__name__, other.__class__.__name__))

@enum_dict
def __ge__(self, other):
    raise TypeError("unorderable types: %s() >= %s()" % (self.__class__.__name__, other.__class__.__name__))

@enum_dict
def __gt__(self, other):
    raise TypeError("unorderable types: %s() > %s()" % (self.__class__.__name__, other.__class__.__name__))


@enum_dict
def __eq__(self, other):
    if isinstance(other, self.__class__):
        return self is other
    return NotImplemented

@enum_dict
def __ne__(self, other):
    if isinstance(other, self.__class__):
        return self is not other
    return NotImplemented


    # enum.property is used to provide access to the `name`, `value', etc.,
    # properties of enum members while keeping some measure of protection
    # from modification, while still allowing for an enumeration to have
    # members named `name`, `value`, etc..  This works because enumeration
    # members are not set directly on the enum class -- enum.property will
    # look them up in _member_map_.

@enum_dict
@property
def name(self):
    return self._name_

@enum_dict
@property
def value(self):
    return self._value_

@enum_dict
@property
def values(self):
    return self._values_

_enum_base = StdlibEnum or object
Enum = EnumType('Enum', (_enum_base, ), enum_dict.resolve())
del enum_dict

    # Enum has now been created

def pickle_by_global_name(self, proto):
    # should not be used with Flag-type enums
    return self.name
_reduce_ex_by_name = pickle_by_global_name

def pickle_by_enum_name(self, proto):
    # should not be used with Flag-type enums
    return getattr, (self.__class__, self._name_)

def _dataclass_repr(self):
    dcf = self.__dataclass_fields__
    return ', '.join(
            '%s=%r' % (k, getattr(self, k))
            for k in dcf.keys()
            if dcf[k].repr
            )

# ReprEnum
if StdlibReprEnum:
    _repr_bases = Enum, StdlibReprEnum
else:
    _repr_bases = (Enum, )
ReprEnum = EnumType('ReprEnum', _repr_bases, {
        '__doc__': "Only changes the repr(), leaving str() and format() to the mixed-in type."
        })

# IntEnum

class IntEnum(int, ReprEnum):
    """
    Enum where members are also (and must be) ints
    """


# StrEnums

class StrEnum(str, ReprEnum):
    """
    Enum where members are also (and must already be) strings

    default value is member name, lower-cased
    """

    def __new__(cls, *values, **kwds):
        if kwds:
            raise TypeError('%r: keyword arguments not supported' % (cls.__name__))
        if values:
            if not isinstance(values[0], str):
                raise TypeError('%s: values must be str [%r is a %r]' % (cls.__name__, values[0], type(values[0])))
        value = str(*values)
        member = str.__new__(cls, value)
        member._value_ = value
        return member

    __str__ = str.__str__

    def _generate_next_value_(name, start, count, last_values):
        """
        Return the lower-cased version of the member name.
        """
        return name.lower()


class LowerStrEnum(StrEnum):
    """
    Enum where members are also (and must already be) lower-case strings

    default value is member name, lower-cased
    """

    def __new__(cls, value, *args, **kwds):
        obj = StrEnum.__new_member__(cls, value, *args, **kwds)
        if value != value.lower():
            raise ValueError('%r is not lower-case' % value)
        return obj


class UpperStrEnum(StrEnum):
    """
    Enum where members are also (and must already be) upper-case strings

    default value is member name, upper-cased
    """

    def __new__(cls, value, *args, **kwds):
        obj = StrEnum.__new_member__(cls, value, *args, **kwds)
        if value != value.upper():
            raise ValueError('%r is not upper-case' % value)
        return obj

    def _generate_next_value_(name, start, count, last_values, *args, **kwds):
        return name.upper()


# Specialty Enums
if PY3:
    class AutoEnum(Enum):
        """
        automatically use _generate_next_value_ when values are missing (Python 3 only)
        """
        _settings_ = MagicValue
    __all__.append('AutoEnum')


class AutoNumberEnum(Enum):
    """
    Automatically assign increasing values to members.

    Py3: numbers match creation order
    Py2: numbers are assigned alphabetically by member name
         (unless `_order_` is specified)
    """

    def __new__(cls, *args, **kwds):
        value = len(cls.__members__) + 1
        if cls._member_type_ is int:
            obj = int.__new__(cls, value)
        elif cls._member_type_ is long:
            obj = long.__new__(cls, value)
        else:
            obj = object.__new__(cls)
        obj._value_ = value
        return obj


class AddValueEnum(Enum):
    _settings_ = AddValue


class MultiValueEnum(Enum):
    """
    Multiple values can map to each member.
    """
    _settings_ = MultiValue


class NoAliasEnum(Enum):
    """
    Duplicate value members are distinct, but cannot be looked up by value.
    """
    _settings_ = NoAlias


class OrderedEnum(Enum):
    """
    Add ordering based on values of Enum members.
    """

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self._value_ >= other._value_
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self._value_ > other._value_
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self._value_ <= other._value_
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self._value_ < other._value_
        return NotImplemented


if sqlite3:
    class SqliteEnum(Enum):
        def __conform__(self, protocol):
            if protocol is sqlite3.PrepareProtocol:
                return self.name


class UniqueEnum(Enum):
    """
    Ensure no duplicate values exist.
    """
    _settings_ = Unique


def convert(enum, name, module, filter, source=None):
    """
    Create a new Enum subclass that replaces a collection of global constants

    enum: Enum, IntEnum, ...
    name: name of new Enum
    module: name of module (__name__ in global context)
    filter: function that returns True if name should be converted to Enum member
    source: namespace to check (defaults to 'module')
    """
    # convert all constants from source (or module) that pass filter() to
    # a new Enum called name, and export the enum and its members back to
    # module;
    # also, replace the __reduce_ex__ method so unpickling works in
    # previous Python versions
    module_globals = vars(_sys.modules[module])
    if source:
        source = vars(source)
    else:
        source = module_globals
    members = dict((name, value) for name, value in source.items() if filter(name))
    enum = enum(name, members, module=module)
    enum.__reduce_ex__ = _reduce_ex_by_name
    module_globals.update(enum.__members__)
    module_globals[name] = enum

def extend_enum(enumeration, name, *args, **kwds):
    """
    Add a new member to an existing Enum.
    """
    # there are four possibilities:
    # - extending an aenum Enum or 3.11+ enum Enum
    # - extending an aenum Flag or 3.11+ enum Flag
    # - extending a pre-3.11 stdlib Enum Flag
    # - extending a 3.11+ stdlib Flag
    #
    # fail early if name is already in the enumeration
    if (
            name in enumeration.__dict__
            or name in enumeration._member_map_
            or name in [t[1] for t in getattr(enumeration, '_value2member_seq_', ())]
        ):
        raise TypeError('%r already in use as %r' % (name, enumeration.__dict__.get(name, enumeration[name])))
    # and check for other instances in parent classes
    descriptor = None
    for base in enumeration.__mro__[1:]:
        descriptor = base.__dict__.get(name)
        if descriptor is not None:
            if isinstance(descriptor, (property, DynamicClassAttribute)):
                break
            else:
                raise TypeError('%r already in use in superclass %r' % (name, base.__name__))
    try:
        _member_map_ = enumeration._member_map_
        _member_names_ = enumeration._member_names_
        _member_type_ = enumeration._member_type_
        _value2member_map_ = enumeration._value2member_map_
        base_attributes = set([a for b in enumeration.mro() for a in b.__dict__])
    except AttributeError:
        raise TypeError('%r is not a supported Enum' % (enumeration, ))
    try:
        _value2member_seq_ = enumeration._value2member_seq_
        _multi_value_ = MultiValue in enumeration._settings_
        _no_alias_ = NoAlias in enumeration._settings_
        _unique_ = Unique in enumeration._settings_
        _auto_init_ = enumeration._auto_init_ or []
    except AttributeError:
        # standard Enum
        _value2member_seq_ = []
        _multi_value_ = False
        _no_alias_ = False
        _unique_ = False
        _auto_init_ = []
    if _multi_value_ and not args:
        # must specify values for multivalue enums
        raise ValueError('no values specified for MultiValue enum %r' % enumeration.__name__)
    mt_new = _member_type_.__new__
    _new = getattr(enumeration, '_new_member_', None) or getattr(enumeration, '__new_member__', None) or mt_new
    if not args:
        last_values = [m.value for m in enumeration]
        count = len(enumeration)
        start = getattr(enumeration, '_start_', None)
        if start is None:
            start = last_values and (last_values[-1] + 1) or 1
        _gnv = getattr(enumeration, '_generate_next_value_', None)
        if _gnv is not None:
            args = ( _gnv(name, start, count, last_values), )
        else:
            # must be a 3.4 or 3.5 Enum
            args = (start, )
    if _new is object.__new__:
        new_uses_args = False
    else:
        new_uses_args = True
    if len(args) == 1:
        [value] = args
    else:
        value = args
    more_values = ()
    kwds = {}
    if isinstance(value, enum):
        args = value.args
        kwds = value.kwds
    if not isinstance(value, tuple):
        args = (value, )
    else:
        args = value
    # tease value out of auto-init if specified
    if 'value' in _auto_init_:
        if 'value' in kwds:
            value = kwds.pop('value')
        else:
            value, args = args[0], args[1:]
    elif _multi_value_:
        value, more_values, args = args[0], args[1:], ()
        if new_uses_args:
            args = (value, )
    if _member_type_ is tuple:
        args = (args, )
    if not new_uses_args:
        new_member = _new(enumeration)
        if not hasattr(new_member, '_value_'):
            new_member._value_ = value
    else:
        new_member = _new(enumeration, *args, **kwds)
        if not hasattr(new_member, '_value_'):
            new_member._value_ = _member_type_(*args)
    value = new_member._value_
    if _multi_value_:
        if 'value' in _auto_init_:
            args = more_values
        else:
        # put all the values back into args for the init call
            args = (value, ) + more_values
    new_member._name_ = name
    new_member.__objclass__ = enumeration.__class__
    new_member.__init__(*args)
    new_member._values_ = (value, ) + more_values
    new_member._sort_order_ = len(enumeration._member_names_)
    # do final checks before modifying enum structures:
    # - is new member a flag?
    #   - does the new member fit in the enum's declared _boundary_?
    # - is new member an alias?
    #
    _all_bits_ = _flag_mask_ = None
    if hasattr(enumeration, '_all_bits_'):
        _all_bits_ = enumeration._all_bits_ | value
        _flag_mask_ = enumeration._flag_mask_ | value
        if enumeration._boundary_ != 'keep':
            missed = list(_iter_bits_lsb(_flag_mask_ & ~_all_bits_))
            if missed:
                raise TypeError(
                        'invalid Flag %r -- missing values: %s'
                        % (cls, ', '.join((str(i) for i in missed)))
                        )
    # If another member with the same value was already defined, the
    # new member becomes an alias to the existing one.
    if _no_alias_:
        # unless NoAlias was specified
        return _finalize_extend_enum(enumeration, new_member, bits=_all_bits_, mask=_flag_mask_)
    else:
        # handle "normal" aliases
        new_values = new_member._values_
        for canonical_member in _member_map_.values():
            canonical_values_ = getattr(canonical_member, '_values_', [canonical_member._value_])
            for canonical_value in canonical_values_:
                for new_value in new_values:
                    if canonical_value == new_value:
                        # name is an alias
                        if _unique_ or _multi_value_:
                            # aliases not allowed in Unique and MultiValue enums
                            raise ValueError('%r is a duplicate of %r' % (new_member, canonical_member))
                        else:
                            # aliased name can be added, remaining checks irrelevant
                            # aliases don't appear in member names (only in __members__ and _member_map_).
                            return _finalize_extend_enum(enumeration, canonical_member, name=name, bits=_all_bits_, mask=_flag_mask_, is_alias=True)
        # not a standard alias, but maybe a flag alias
        if pyver < PY3_6:
            flag_bases = Flag,
        else:
            flag_bases = Flag, StdlibFlag
        if issubclass(enumeration, flag_bases) and hasattr(enumeration, '_all_bits_'):
            # handle the new flag type
            if is_single_bit(value):
                # a new member!  (an aliase would have been discovered in the previous loop)
                return _finalize_extend_enum(enumeration, new_member, bits=_all_bits_, mask=_flag_mask_)
            else:
                # might be an 3.11 Flag alias
                if value & enumeration._flag_mask_ == value and _value2member_map_.get(value) is not None:
                    # yup, it's an alias to existing members... and its an alias of an alias
                    canonical = _value2member_map_.get(value)
                    return _finalize_extend_enum(enumeration, canonical, name=name, bits=_all_bits_, mask=_flag_mask_, is_alias=True)
                else:
                    return _finalize_extend_enum(enumeration, new_member, bits=_all_bits_, mask=_flag_mask_, is_alias=True)
        else:
            # if we get here, we have a brand new member
            return _finalize_extend_enum(enumeration, new_member)

def _finalize_extend_enum(enumeration, new_member, name=None, bits=None, mask=None, is_alias=False):
    name = name or new_member.name
    descriptor = None
    for base in enumeration.__mro__[1:]:
        descriptor = base.__dict__.get(name)
        if descriptor is not None:
            if isinstance(descriptor, (property, DynamicClassAttribute)):
                break
            else:
                raise TypeError('%r already in use in superclass %r' % (name, base.__name__))
    if not descriptor:
        # get redirect in place before adding to _member_map_
        redirect = property()
        redirect.__set_name__(enumeration, name)
        setattr(enumeration, name, redirect)
    if not is_alias:
        enumeration._member_names_.append(name)
    enumeration._member_map_[name] = new_member
    for v in getattr(new_member, '_values_', [new_member._value_]):
        try:
            enumeration._value2member_map_[v] = new_member
        except TypeError:
            enumeration._value2member_seq_ += ((v, new_member), )
    if bits:
        enumeration._all_bits_ = bits
        enumeration._flag_mask_ = mask
        if is_single_bit(new_member._value_):
            enumeration._singles_mask_ |= new_member._value_
    return new_member

def unique(enumeration):
    """
    Class decorator that ensures only unique members exist in an enumeration.
    """
    duplicates = []
    for name, member in enumeration.__members__.items():
        if name != member.name:
            duplicates.append((name, member.name))
    if duplicates:
        duplicate_names = ', '.join(
                ["%s -> %s" % (alias, name) for (alias, name) in duplicates]
                )
        raise ValueError('duplicate names found in %r: %s' %
                (enumeration, duplicate_names)
                )
    return enumeration

# Flag

try:
    from enum import FlagBoundary
except ImportError:
    class FlagBoundary(StrEnum):
        """
        control how out of range values are handled
        "strict" -> error is raised  [default]
        "conform" -> extra bits are discarded
        "eject" -> lose flag status (becomes a normal integer)
        """
        STRICT = auto()
        CONFORM = auto()
        EJECT = auto()
        KEEP = auto()
export(FlagBoundary, globals())

if StdlibFlag:
    _flag_bases = Enum, StdlibFlag
else:
    _flag_bases = (Enum, )

flag_dict = _Addendum(
        dict=EnumType.__prepare__('Flag', _flag_bases),
        doc="Generic flag enumeration.\n\nDerive from this class to define new flag enumerations.",
        ns=globals(),
        )

flag_dict['_boundary_'] = STRICT
flag_dict['_numeric_repr_'] = repr

@flag_dict
def _generate_next_value_(name, start, count, last_values, *args, **kwds):
    """
    Generate the next value when not given.

    name: the name of the member
    start: the initital start value or None
    count: the number of existing members
    last_value: the last value assigned or None
    """
    if not count:
        if args:
            return ((1, start)[start is not None], ) + args
        else:
            return (1, start)[start is not None]
    else:
        last_value = max(last_values)
        try:
            high_bit = _high_bit(last_value)
            result = 2 ** (high_bit+1)
            if args:
                return (result,)  + args
            else:
                return result
        except Exception:
            pass
        raise TypeError('invalid Flag value: %r' % last_value)

@flag_dict
@classmethod
def _iter_member_by_value_(cls, value):
    """
    Extract all members from the value in definition (i.e. increasing value) order.
    """
    for val in _iter_bits_lsb(value & cls._singles_mask_):
        yield cls._value2member_map_.get(val)

flag_dict['_iter_member_'] = _iter_member_by_value_

@flag_dict
@classmethod
def _iter_member_by_def_(cls, value):
    """
    Extract all members from the value in definition order.
    """
    members = list(cls._iter_member_by_value_(value))
    members.sort(key=lambda m: m._sort_order_)
    for member in members:
        yield member

@flag_dict
@classmethod
def _missing_(cls, value):
    """
    return a member matching the given value, or None
    """
    return cls._create_pseudo_member_(value)

@flag_dict
@classmethod
def _create_pseudo_member_(cls, *values):
    """
    Create a composite member.
    """
    # if we get here, no exact match was found
    # STRICT - must be composed of single-bit flags
    value = error_value = values[0]
    if not isinstance(value, baseinteger):
        raise ValueError(
                "%r is not a valid %s" % (error_value, cls.__name__)
                )
    # check boundaries
    # - value must be in range (e.g. -16 <-> +15, i.e. ~15 <-> 15)
    # - value must not include any skipped flags (e.g. if bit 2 is not
    #   defined, then 0d10 is invalid)
    flag_mask = cls._flag_mask_
    singles_mask = cls._singles_mask_
    all_bits = cls._all_bits_
    unknown_bits = all_bits ^ flag_mask
    unnamed_bits = all_bits & ~flag_mask
    boundary = cls._boundary_
    neg_value = (None, value)[value < 0]
    #
    if neg_value:
        if neg_value <= ~all_bits:
            if boundary is EJECT:
                return error_value
            elif boundary is KEEP:
                value = 2**(neg_value.bit_length()) + neg_value
            elif boundary is CONFORM:
                value = (2**(neg_value.bit_length()) + neg_value) & flag_mask
            else:
                raise ValueError(
                        "%r is not a valid %s" % (error_value, cls.__name__)
                        )
        else:
            value = all_bits + 1 + neg_value
    #
    member_value = value & singles_mask                     # all named single-bit values
    unnamed_value = value & flag_mask & ~singles_mask       # all unnamed single-bit values
    unknown_value = value & ~flag_mask
    #
    if boundary is EJECT:
        if unknown_value:
            return error_value
    elif boundary is CONFORM:
        unknown_value = 0
    elif boundary is STRICT:
        if unknown_value:
            raise ValueError(
                "%r is not a valid %s" % (error_value, cls.__name__)
                    )
    #
    members = list(cls._iter_member_(member_value))
    final_value = member_value
    still_unknown = 0
    if unnamed_value:
        found = 0
        for n, pm in cls._member_map_.items():
            if (
                    pm not in members
                and pm._value_
                and pm._value_ & final_value == pm._value_
                and pm._value_ & unnamed_value
                ):
                members.append(pm)
                final_value |= pm._value_
                found |= pm._value_
        # anything still unnamed becomes unknown
        still_unknown = (found & ~unnamed_value) ^ unnamed_value
        if still_unknown:
            if boundary is KEEP:
                pass
            elif boundary is CONFORM:
                still_unknown = 0
            elif boundary is EJECT:
                return error_value
            else: # strict
                raise ValueError(
                    "%r is not a valid %s" % (error_value, cls.__name__)
                        )
    unknown_value |= still_unknown
    final_value |= unknown_value
    values = (final_value, ) + values[1:]
    members.sort(key=lambda m: m._sort_order_)
    # let class adjust values
    values = cls._create_pseudo_member_values_(members, *values)
    __new__ = getattr(cls, '__new_member__', None)
    if cls._member_type_ is object and not __new__:
        # construct a singleton enum pseudo-member
        pseudo_member = object.__new__(cls)
    else:
        pseudo_member = (__new__ or cls._member_type_.__new__)(cls, *values)
    if not hasattr(pseudo_member, '_value_'):
        pseudo_member._value_ = final_value
    if members:
        pseudo_member._name_ = '|'.join([m._name_ for m in members])
        if unknown_value:
            pseudo_member._name_ += '|%s' % cls._numeric_repr_(unknown_value)
    else:
        pseudo_member._name_ = None
    # use setdefault in case another thread already created a composite
    # with this value, but only if all members are known
    # note: zero is a special case -- always add it
    pseudo_member = cls._value2member_map_.setdefault(final_value, pseudo_member)
    if neg_value is not None:
        cls._value2member_map_[neg_value] = pseudo_member
    return pseudo_member

@flag_dict
@classmethod
def _create_pseudo_member_values_(cls, members, *values):
    """
    Return values to be fed to __new__ to create new member.
    """
    if cls._member_type_ in (baseinteger + (object, )):
        return values
    elif len(values) < 2:
        return values + (cls._member_type_(), )
    else:
        return values

@flag_dict
def __contains__(self, other):
    """
    Returns True if self has at least the same flags set as other.
    """
    if not isinstance(other, self.__class__):
        raise TypeError(
            "unsupported operand type(s) for 'in': '%s' and '%s'" % (
                type(other).__name__, self.__class__.__name__))
    if other._value_ == 0 or self._value_ == 0:
        return False
    return other._value_ & self._value_ == other._value_

@flag_dict
def __iter__(self):
    """
    Returns flags in definition order.
    """
    for member in self._iter_member_(self._value_):
        yield member

@flag_dict
def __len__(self):
    return bit_count(self._value_)

@flag_dict
def __repr__(self):
    cls = self.__class__
    if self._name_ is None:
        # only zero is unnamed by default
        return '<%s: %r>' % (cls.__name__, self._value_)
    else:
        return '<%s.%s: %r>' % (cls.__name__, self._name_, self._value_)

@flag_dict
def __str__(self):
    cls = self.__class__
    if self._name_ is None:
        return '%s(%s)' % (cls.__name__, self._value_)
    else:
        return '%s.%s' % (cls.__name__, self._name_)

if PY2:
    @flag_dict
    def __nonzero__(self):
        return bool(self._value_)
else:
    @flag_dict
    def __bool__(self):
        return bool(self._value_)

@flag_dict
def __or__(self, other):
    if isinstance(other, self.__class__):
        other_value = other._value_
    elif self._member_type_ is not object and isinstance(other, self._member_type_):
        other_value = other
    else:
        return NotImplemented
    return self.__class__(self._value_ | other_value)

@flag_dict
def __and__(self, other):
    if isinstance(other, self.__class__):
        other_value = other._value_
    elif self._member_type_ is not object and isinstance(other, self._member_type_):
        other_value = other
    else:
        return NotImplemented
    return self.__class__(self._value_ & other_value)

@flag_dict
def __xor__(self, other):
    if isinstance(other, self.__class__):
        other_value = other._value_
    elif self._member_type_ is not object and isinstance(other, self._member_type_):
        other_value = other
    else:
        return NotImplemented
    return self.__class__(self._value_ ^ other_value)

@flag_dict
def __invert__(self):
    if self._inverted_ is None:
        self._inverted_ = self.__class__(self._singles_mask_ & ~self._value_)
        if isinstance(self._inverted_, self.__class__):
            self._inverted_._inverted_ = self
    return self._inverted_

flag_dict['__ror__'] = __or__
flag_dict['__rand__'] = __and__
flag_dict['__rxor__'] = __xor__

Flag = EnumType('Flag', _flag_bases, flag_dict.resolve())
del(flag_dict)

# IntFlag

class IntFlag(int, ReprEnum, Flag):
    "Support for integer-based Flags"

    _boundary_ = KEEP

    def __contains__(self, other):
        """
        Returns True if self has at least the same flags set as other.
        """
        if isinstance(other, int):
            other = self.__class__(other)
        elif not isinstance(other, self.__class__):
            raise TypeError(
                "unsupported operand type(s) for 'in': '%s' and '%s'" % (
                    type(other).__name__, self.__class__.__name__))
        if other._value_ == 0 or self._value_ == 0:
            return False
        return other._value_ & self._value_ == other._value_


# helpers

def _high_bit(value):
    """returns index of highest bit, or -1 if value is zero or negative"""
    return value.bit_length() - 1

def global_enum_repr(self):
    """
    use module.enum_name instead of class.enum_name

    the module is the last module in case of a multi-module name
    """
    module = self.__class__.__module__.split('.')[-1]
    return '%s.%s' % (module, self._name_)

def global_flag_repr(self):
    """
    use module.flag_name instead of class.flag_name

    the module is the last module in case of a multi-module name
    """
    module = self.__class__.__module__.split('.')[-1]
    cls_name = self.__class__.__name__
    if self._name_ is None:
        return "%s.%s(%r)" % (module, cls_name, self._value_)
    if is_single_bit(self):
        return '%s.%s' % (module, self._name_)
    if self._boundary_ is not FlagBoundary.KEEP:
        return '|'.join(['%s.%s' % (module, name) for name in self.name.split('|')])
    else:
        name = []
        for n in self._name_.split('|'):
            if n[0].isdigit():
                name.append(n)
            else:
                name.append('%s.%s' % (module, n))
        return '|'.join(name)

def global_str(self):
    """
    use enum_name instead of class.enum_name
    """
    if self._name_ is None:
        cls_name = self.__class__.__name__
        return "%s(%r)" % (cls_name, self._value_)
    else:
        return self._name_

def global_enum(cls, update_str=False):
    """
    decorator that makes the repr() of an enum member reference its module
    instead of its class; also exports all members to the enum's module's
    global namespace
    """
    if issubclass(cls, Flag):
        cls.__repr__ = global_flag_repr
    else:
        cls.__repr__ = global_enum_repr
    if not issubclass(cls, ReprEnum) or update_str:
        cls.__str__ = global_str
    _sys.modules[cls.__module__].__dict__.update(cls.__members__)
    return cls

if StdlibEnumMeta:

    from _weakrefset import WeakSet

    def __subclasscheck__(cls, subclass):
        """
        Override for issubclass(subclass, cls).
        """
        if not isinstance(subclass, type):
            raise TypeError('issubclass() arg 1 must be a class (got %r)' % (subclass, ))
        # Check cache
        try:
            cls.__dict__['_subclass_cache_']
        except KeyError:
            cls._subclass_cache_ = WeakSet()
            cls._subclass_negative_cache_ = WeakSet()
        except RecursionError:
            import sys
            exc, cls, tb = sys.exc_info()
            exc = RecursionError('possible causes for endless recursion:\n    - __getattribute__ is not ignoring __dunder__ attibutes\n    - __instancecheck__ and/or __subclasscheck_ are (mutually) recursive\n    see `aenum.remove_stdlib_integration` for temporary work-around')
            raise_from_none(exc)
        if subclass in cls._subclass_cache_:
            return True
        # Check negative cache
        elif subclass in cls._subclass_negative_cache_:
            return False
        if cls is subclass:
            cls._subclass_cache_.add(subclass)
            return True
        # Check if it's a direct subclass
        if cls in getattr(subclass, '__mro__', ()):
            cls._subclass_cache_.add(subclass)
            return True
        # Check if it's an aenum.Enum|IntEnum|IntFlag|Flag subclass
        if cls is StdlibIntFlag and issubclass(subclass, IntFlag):
            cls._subclass_cache_.add(subclass)
            return True
        elif cls is StdlibFlag and issubclass(subclass, Flag):
            cls._subclass_cache_.add(subclass)
            return True
        elif cls is StdlibIntEnum and issubclass(subclass, IntEnum):
            cls._subclass_cache_.add(subclass)
            return True
        if cls is StdlibEnum and issubclass(subclass, Enum):
            cls._subclass_cache_.add(subclass)
            return True
        # No dice; update negative cache
        cls._subclass_negative_cache_.add(subclass)
        return False

    def __instancecheck__(cls, instance):
        subclass = instance.__class__
        try:
            return cls.__subclasscheck__(subclass)
        except RecursionError:
            import sys
            exc, cls, tb = sys.exc_info()
            exc = RecursionError('possible causes for endless recursion:\n    - __getattribute__ is not ignoring __dunder__ attibutes\n    - __instancecheck__ and/or __subclasscheck_ are (mutually) recursive\n    see `aenum.remove_stdlib_integration` for temporary work-around')
            raise_from_none(exc)


def add_stdlib_integration():
    if StdlibEnum:
        StdlibEnumMeta.__subclasscheck__ = __subclasscheck__
        StdlibEnumMeta.__instancecheck__ = __instancecheck__

def remove_stdlib_integration():
    """
    Remove the __instancecheck__ and __subclasscheck__ overrides from the stdlib Enum.

    Those overrides are in place so that code detecting stdlib enums will also detect
    aenum enums.  If a buggy __getattribute__, __instancecheck__, or __subclasscheck__
    is defined on a custom EnumMeta then RecursionErrors can result; using this
    function after importing aenum will solve that problem, but the better solution is
    to fix the buggy method.
    """
    if StdlibEnum:
        del StdlibEnumMeta.__instancecheck__
        del StdlibEnumMeta.__subclasscheck__

class cls2module(object):
    def __init__(self, cls, *args):
        self.__name__ = cls.__name__
        self._parent_module = cls.__module__
        self.__all__ = []
        all_objects = cls.__dict__
        if not args:
            args = [k for k, v in all_objects.items() if isinstance(v, (NamedConstant, Enum))]
        for name in args:
            self.__dict__[name] = all_objects[name]
            self.__all__.append(name)
    def register(self):
        _sys.modules["%s.%s" % (self._parent_module, self.__name__)] = self


