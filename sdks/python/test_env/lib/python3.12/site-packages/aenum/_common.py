from __future__ import print_function

__all__ = [
        'pyver', 'PY2', 'PY2_6', 'PY3', 'PY3_3', 'PY3_4', 'PY3_5', 'PY3_6', 'PY3_7', 'PY3_11',
        '_or_', '_and_', '_xor_', '_inv_', '_abs_', '_add_', '_floordiv_', '_lshift_',
        '_rshift_', '_mod_', '_mul_', '_neg_', '_pos_', '_pow_', '_truediv_', '_sub_',
        'unicode', 'basestring', 'baseinteger', 'long', 'NoneType', '_Addendum',
        'is_descriptor', 'is_dunder', 'is_sunder', 'is_internal_class', 'is_private_name',
        'get_attr_from_chain', '_value', 'constant',
        'make_class_unpicklable', 'bltin_property',
        'skip', 'nonmember', 'member', 'Member', 'NonMember', 'OrderedDict',
        ]


# imports
import sys as _sys
pyver = _sys.version_info[:2]
PY2 = pyver < (3, )
PY3 = pyver >= (3, )
PY2_6 = (2, 6)
PY3_3 = (3, 3)
PY3_4 = (3, 4)
PY3_5 = (3, 5)
PY3_6 = (3, 6)
PY3_7 = (3, 7)
PY3_11 = (3, 11)

import re

from operator import or_ as _or_, and_ as _and_, xor as _xor_, inv as _inv_
from operator import abs as _abs_, add as _add_, floordiv as _floordiv_
from operator import lshift as _lshift_, rshift as _rshift_, mod as _mod_
from operator import mul as _mul_, neg as _neg_, pos as _pos_, pow as _pow_
from operator import truediv as _truediv_, sub as _sub_

if PY2:
    from . import _py2
    from ._py2 import *
    __all__.extend(_py2.__all__)
if PY3:
    from . import _py3
    from ._py3 import *
    __all__.extend(_py3.__all__)

bltin_property = property

# shims

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

try:
    unicode
    unicode = unicode
except NameError:
    # In Python 3 unicode no longer exists (it's just str)
    unicode = str

try:
    basestring
    basestring = bytes, unicode
except NameError:
    # In Python 2 basestring is the ancestor of both str and unicode
    # in Python 3 it's just str, but was missing in 3.1
    basestring = str,

try:
    baseinteger = int, long
    long = long
except NameError:
    baseinteger = int,
    long = int
# deprecated
baseint = baseinteger

try:
    NoneType
except NameError:
    NoneType = type(None)

class _Addendum(object):
    def __init__(self, dict, doc, ns):
        # dict is the dict to update with functions
        # doc is the docstring to put in the dict
        # ns is the namespace to remove the function names from
        self.dict = dict
        self.ns = ns
        self.added = set()
    def __call__(self, func):
        if isinstance(func, (staticmethod, classmethod)):
            name = func.__func__.__name__
        elif isinstance(func, (property, bltin_property)):
            name = (func.fget or func.fset or func.fdel).__name__
        else:
            name = func.__name__
        self.dict[name] = func
        self.added.add(name)
        return func
    def __getitem__(self, name):
        return self.dict[name]
    def __setitem__(self, name, value):
        self.dict[name] = value
    def resolve(self):
        ns = self.ns
        for name in self.added:
            del ns[name]
        return self.dict

def is_descriptor(obj):
    """Returns True if obj is a descriptor, False otherwise."""
    return (
            hasattr(obj, '__get__') or
            hasattr(obj, '__set__') or
            hasattr(obj, '__delete__'))


def is_dunder(name):
    """Returns True if a __dunder__ name, False otherwise."""
    return (len(name) > 4 and
            name[:2] == name[-2:] == '__' and
            name[2] != '_' and
            name[-3] != '_')


def is_sunder(name):
    """Returns True if a _sunder_ name, False otherwise."""
    return (len(name) > 2 and
            name[0] == name[-1] == '_' and
            name[1] != '_' and
            name[-2] != '_')

def is_internal_class(cls_name, obj):
    # only 3.3 and up, always return False in 3.2 and below
    if pyver < PY3_3:
        return False
    else:
        qualname = getattr(obj, '__qualname__', False)
        return not is_descriptor(obj) and qualname and re.search(r"\.?%s\.\w+$" % cls_name, qualname)

def is_private_name(cls_name, name):
    pattern = r'^_%s__\w+[^_]_?$' % (cls_name, )
    return re.search(pattern, name)

def get_attr_from_chain(cls, attr):
    sentinel = object()
    for basecls in cls.mro():
        obj = basecls.__dict__.get(attr, sentinel)
        if obj is not sentinel:
            return obj

def _value(obj):
    if isinstance(obj, (auto, constant)):
        return obj.value
    else:
        return obj

class constant(object):
    '''
    Simple constant descriptor for NamedConstant and Enum use.
    '''
    def __init__(self, value, doc=None):
        self.value = value
        self.__doc__ = doc
    def __get__(self, *args):
        return self.value
    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.value)
    def __and__(self, other):
        return _and_(self.value, _value(other))
    def __rand__(self, other):
        return _and_(_value(other), self.value)
    def __invert__(self):
        return _inv_(self.value)
    def __or__(self, other):
        return _or_(self.value, _value(other))
    def __ror__(self, other):
        return _or_(_value(other), self.value)
    def __xor__(self, other):
        return _xor_(self.value, _value(other))
    def __rxor__(self, other):
        return _xor_(_value(other), self.value)
    def __abs__(self):
        return _abs_(self.value)
    def __add__(self, other):
        return _add_(self.value, _value(other))
    def __radd__(self, other):
        return _add_(_value(other), self.value)
    def __neg__(self):
        return _neg_(self.value)
    def __pos__(self):
        return _pos_(self.value)
    if PY2:
        def __div__(self, other):
            return _div_(self.value, _value(other))
    def __rdiv__(self, other):
        return _div_(_value(other), (self.value))
    def __floordiv__(self, other):
        return _floordiv_(self.value, _value(other))
    def __rfloordiv__(self, other):
        return _floordiv_(_value(other), self.value)
    def __truediv__(self, other):
        return _truediv_(self.value, _value(other))
    def __rtruediv__(self, other):
        return _truediv_(_value(other), self.value)
    def __lshift__(self, other):
        return _lshift_(self.value, _value(other))
    def __rlshift__(self, other):
        return _lshift_(_value(other), self.value)
    def __rshift__(self, other):
        return _rshift_(self.value, _value(other))
    def __rrshift__(self, other):
        return _rshift_(_value(other), self.value)
    def __mod__(self, other):
        return _mod_(self.value, _value(other))
    def __rmod__(self, other):
        return _mod_(_value(other), self.value)
    def __mul__(self, other):
        return _mul_(self.value, _value(other))
    def __rmul__(self, other):
        return _mul_(_value(other), self.value)
    def __pow__(self, other):
        return _pow_(self.value, _value(other))
    def __rpow__(self, other):
        return _pow_(_value(other), self.value)
    def __sub__(self, other):
        return _sub_(self.value, _value(other))
    def __rsub__(self, other):
        return _sub_(_value(other), self.value)
    def __set_name__(self, ownerclass, name):
        self.name = name
        self.clsname = ownerclass.__name__

def make_class_unpicklable(obj):
    """
    Make the given obj un-picklable.

    obj should be either a dictionary, on an Enum
    """
    def _break_on_call_reduce(self, proto):
        raise TypeError('%r cannot be pickled' % self)
    if isinstance(obj, dict):
        obj['__reduce_ex__'] = _break_on_call_reduce
        obj['__module__'] = '<unknown>'
    else:
        setattr(obj, '__reduce_ex__', _break_on_call_reduce)
        setattr(obj, '__module__', '<unknown>')

class NonMember(object):
    """
    Protects item from becaming an Enum member during class creation.
    """
    def __init__(self, value):
        self.value = value

    def __get__(self, instance, ownerclass=None):
        return self.value
skip = nonmember = NonMember

class Member(object):
    """
    Forces item to became an Enum member during class creation.
    """
    def __init__(self, value):
        self.value = value
member = Member


