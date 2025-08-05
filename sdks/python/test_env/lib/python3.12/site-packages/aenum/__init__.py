"""Python Advanced Enumerations & NameTuples"""
from __future__ import print_function

version = 3, 1, 15

# imports
from ._common import *
from ._constant import *
from ._tuple import *
from ._enum import *


__all__ = [
        'NamedConstant', 'Constant', 'constant', 'skip', 'nonmember', 'member', 'no_arg',
        'Member', 'NonMember', 'bin', 
        'Enum', 'IntEnum', 'AutoNumberEnum', 'OrderedEnum', 'UniqueEnum',
        'StrEnum', 'UpperStrEnum', 'LowerStrEnum', 'ReprEnum',
        'Flag', 'IntFlag', 'enum_property',
        'AddValue', 'MagicValue', 'MultiValue', 'NoAlias', 'Unique',
        'AddValueEnum', 'MultiValueEnum', 'NoAliasEnum',
        'enum', 'extend_enum', 'unique', 'property',
        'NamedTuple', 'SqliteEnum', '_reduce_ex_by_name',
        'FlagBoundary', 'STRICT', 'CONFORM', 'EJECT', 'KEEP',
        'add_stdlib_integration', 'remove_stdlib_integration'
        ]

if sqlite3 is None:
    __all__.remove('SqliteEnum')


if PY2:
    from . import _py2
    __all__.extend(_py2.__all__)
else:
    from . import _py3
    __all__.extend(_py3.__all__)
    __all__.append('AutoEnum')



# helpers

