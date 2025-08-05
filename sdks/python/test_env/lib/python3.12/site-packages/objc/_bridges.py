import collections.abc
import datetime
import pathlib

from objc import _objc

__all__ = [
    "registerListType",
    "registerMappingType",
    "registerSetType",
    "registerDateType",
    "registerPathType",
]

_objc.options._datetime_date_type = datetime.date
_objc.options._datetime_datetime_type = datetime.datetime


def registerListType(type_object):
    """
    Register 'type' as a list-like type that will be proxied
    as an NSMutableArray subclass.
    """
    if _objc.options._sequence_types is None:
        _objc.options._sequence_types = ()

    _objc.options._sequence_types += (type_object,)


def registerMappingType(type_object):
    """
    Register 'type' as a dictionary-like type that will be proxied
    as an NSMutableDictionary subclass.
    """
    if _objc.options._mapping_types is None:
        _objc.options._mapping_types = ()

    _objc.options._mapping_types += (type_object,)


def registerSetType(type_object):
    """
    Register 'type' as a set-like type that will be proxied
    as an NSMutableSet subclass.
    """
    if _objc.options._set_types is None:
        _objc.options._set_types = ()

    _objc.options._set_types += (type_object,)


def registerDateType(type_object):
    """
    Register 'type' as a date-like type that will be proxied
    as an NSDate subclass.
    """
    if _objc.options._date_types is None:
        _objc.options._date_types = ()

    _objc.options._date_types += (type_object,)


def registerPathType(type_object):
    """
    Register 'type' as a date-like type that will be proxied
    as an NSDate subclass.
    """
    if _objc.options._path_types is None:
        _objc.options._path_types = ()

    _objc.options._path_types += (type_object,)


registerListType(collections.abc.Sequence)
registerListType(range)
registerMappingType(collections.abc.Mapping)
registerMappingType(dict)
registerSetType(set)
registerSetType(frozenset)
registerSetType(collections.abc.Set)
registerDateType(datetime.date)
registerDateType(datetime.datetime)
registerPathType(pathlib.Path)
