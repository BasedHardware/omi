"""
Conversion.py -- Tools for converting between Python and Objective-C objects.

Conversion offers API to convert between Python and Objective-C instances of
various classes.   Currently, the focus is on Python and Objective-C
collections.
"""

__all__ = [
    "pythonCollectionFromPropertyList",
    "propertyListFromPythonCollection",
    "serializePropertyList",
    "deserializePropertyList",
    "toPythonDecimal",
    "fromPythonDecimal",
]

import datetime
import decimal
import time

import Foundation
import objc
from objc._pythonify import OC_PythonFloat, OC_PythonLong

PYTHON_TYPES = (
    str,
    bool,
    int,
    float,
    list,
    tuple,
    dict,
    set,
    datetime.date,
    datetime.datetime,
    bool,
    type(None),
    bytes,
)

DECIMAL_LOCALE = Foundation.NSDictionary.dictionaryWithObject_forKey_(
    ".", "NSDecimalSeparator"
)


def toPythonDecimal(aNSDecimalNumber):
    """
    Convert a NSDecimalNumber to a Python decimal.Decimal
    """
    return decimal.Decimal(aNSDecimalNumber.descriptionWithLocale_(DECIMAL_LOCALE))


def fromPythonDecimal(aPythonDecimal):
    """
    Convert a Python decimal.Decimal to a NSDecimalNumber
    """
    value_str = str(aPythonDecimal)

    return Foundation.NSDecimalNumber.decimalNumberWithString_locale_(
        value_str, DECIMAL_LOCALE
    )


FORMATS = {
    "xml": Foundation.NSPropertyListXMLFormat_v1_0,
    "binary": Foundation.NSPropertyListBinaryFormat_v1_0,
    "ascii": Foundation.NSPropertyListOpenStepFormat,
}


def serializePropertyList(aPropertyList, format="xml"):  # noqa: A002
    """
    Serialize a property list to an NSData object.  Format is one of the
    following strings:

    xml (default):
        NSPropertyListXMLFormat_v1_0, the XML representation

    binary:
        NSPropertyListBinaryFormat_v1_0, the efficient binary representation

    ascii:
        NSPropertyListOpenStepFormat, the old-style ASCII property list

    It is expected that this property list is comprised of Objective-C
    objects.  In most cases Python data structures will work, but
    decimal.Decimal and datetime.datetime objects are not transparently
    bridged so it will fail in that case.  If you expect to have these
    objects in your property list, then use propertyListFromPythonCollection
    before serializing it.
    """
    try:
        formatOption = FORMATS[format]
    except KeyError:
        raise ValueError(f"Invalid format: {format}")
    (
        data,
        err,
    ) = Foundation.NSPropertyListSerialization.dataFromPropertyList_format_errorDescription_(  # noqa: B950
        aPropertyList, formatOption, None
    )
    if err is not None:
        raise ValueError(err)
    return data


def deserializePropertyList(propertyListData):
    """
    Deserialize a property list from a NSData, str or bytes object

    Returns an Objective-C property list.
    """
    if isinstance(propertyListData, str):
        propertyListData = propertyListData.encode("utf-8")
    (
        plist,
        fmt,
        err,
    ) = Foundation.NSPropertyListSerialization.propertyListFromData_mutabilityOption_format_errorDescription_(  # noqa: B950
        propertyListData, Foundation.NSPropertyListMutableContainers, None, None
    )
    if err is not None:
        raise ValueError(err)
    return plist


def propertyListFromPythonCollection(aPyCollection, conversionHelper=None):
    """
    Convert a Python collection (dict, list, tuple, string) into an
    Objective-C collection.

    If conversionHelper is defined, it must be a callable.  It will be called
    for any object encountered for which propertyListFromPythonCollection()
    cannot automatically convert the object.   The supplied helper function
    should convert the object and return the converted form.  If the conversion
    helper cannot convert the type, it should raise an exception or return
    None.
    """
    if isinstance(aPyCollection, dict):
        collection = Foundation.NSMutableDictionary.dictionary()
        for aKey in aPyCollection:
            if not isinstance(aKey, str):
                raise TypeError("Property list keys must be strings")
            convertedValue = propertyListFromPythonCollection(
                aPyCollection[aKey], conversionHelper=conversionHelper
            )
            collection[aKey] = convertedValue
        return collection
    elif isinstance(aPyCollection, (list, tuple)):
        collection = Foundation.NSMutableArray.array()
        for aValue in aPyCollection:
            convertedValue = propertyListFromPythonCollection(
                aValue, conversionHelper=conversionHelper
            )
            collection.append(convertedValue)
        return collection
    elif isinstance(aPyCollection, (datetime.datetime, datetime.date)):
        return Foundation.NSDate.dateWithTimeIntervalSince1970_(
            time.mktime(aPyCollection.timetuple())
        )
    elif isinstance(aPyCollection, (set, frozenset)):
        collection = Foundation.NSMutableSet.set()
        for aValue in aPyCollection:
            convertedValue = propertyListFromPythonCollection(
                aValue, conversionHelper=conversionHelper
            )
            collection.add(convertedValue)
        return collection

    elif isinstance(aPyCollection, decimal.Decimal):
        return fromPythonDecimal(aPyCollection)
    elif isinstance(aPyCollection, PYTHON_TYPES):
        # bridge will convert
        return aPyCollection
    elif conversionHelper is not None:
        return conversionHelper(aPyCollection)
    raise TypeError(
        "Type '%s' encountered in Python collection; don't know how to convert."
        % type(aPyCollection)
    )


def pythonCollectionFromPropertyList(aCollection, conversionHelper=None):
    """
    Converts a Foundation based property list into a Python
    collection (all members will be instances or subclasses of standard Python
    types)

    Like propertyListFromPythonCollection(), conversionHelper is an optional
    callable that will be invoked any time an encountered object cannot be
    converted.
    """
    if isinstance(aCollection, Foundation.NSDictionary):
        pyCollection = {}
        for k in aCollection:
            convertedValue = pythonCollectionFromPropertyList(
                aCollection[k], conversionHelper
            )
            pyCollection[pythonCollectionFromPropertyList(k)] = convertedValue
        return pyCollection
    elif isinstance(aCollection, Foundation.NSArray):
        return [
            pythonCollectionFromPropertyList(item, conversionHelper)
            for item in aCollection
        ]

    elif isinstance(aCollection, Foundation.NSSet):
        value = set()
        for item in aCollection:
            item = pythonCollectionFromPropertyList(item, conversionHelper)
            if isinstance(item, list):
                item = tuple(item)

            value.add(item)
        return value
    elif isinstance(aCollection, Foundation.NSData):
        return bytes(aCollection)
    elif isinstance(aCollection, Foundation.NSDate):
        return datetime.datetime.fromtimestamp(aCollection.timeIntervalSince1970())
    elif isinstance(aCollection, (objc.pyobjc_unicode, Foundation.NSString)):
        return str(aCollection)
    elif isinstance(aCollection, OC_PythonLong):
        return int(aCollection)
    elif isinstance(aCollection, OC_PythonFloat):
        return float(aCollection)
    elif isinstance(aCollection, Foundation.NSDecimalNumber):
        return toPythonDecimal(aCollection)
    elif aCollection is Foundation.NSNull.null():
        return None
    elif isinstance(aCollection, PYTHON_TYPES):
        return aCollection
    elif conversionHelper:
        return conversionHelper(aCollection)
    raise TypeError(
        "Type '%s' encountered in ObjC collection;  don't know how to convert."
        % type(aCollection)
    )
