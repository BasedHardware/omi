import CoreFoundation as _CF
import objc as _objc


#
# 'Emulation' for CFArray constructors
#
def _setup():
    NSArray = _objc.lookUpClass("NSArray")
    NSMutableArray = _objc.lookUpClass("NSMutableArray")

    def CFArrayCreate(allocator, values, numvalues, callbacks):
        assert callbacks is None
        return NSArray.alloc().initWithArray_(values[:numvalues])

    def CFArrayCreateMutable(allocator, capacity, callbacks):
        assert callbacks is None
        return NSMutableArray.alloc().init()

    return CFArrayCreate, CFArrayCreateMutable


CFArrayCreate, CFArrayCreateMutable = _setup()

# CFDictionary emulation functions


def _setup():
    NSDictionary = _objc.lookUpClass("NSDictionary")
    NSMutableDictionary = _objc.lookUpClass("NSMutableDictionary")

    def CFDictionaryCreate(
        allocator, keys, values, numValues, keyCallbacks, valueCallbacks
    ):
        assert keyCallbacks is None
        assert valueCallbacks is None

        keys = list(keys)[:numValues]
        values = list(values)[:numValues]

        return NSDictionary.dictionaryWithDictionary_(dict(zip(keys, values)))

    def CFDictionaryCreateMutable(allocator, capacity, keyCallbacks, valueCallbacks):
        assert keyCallbacks is None
        assert valueCallbacks is None

        return NSMutableDictionary.dictionary()

    return CFDictionaryCreate, CFDictionaryCreateMutable


CFDictionaryCreate, CFDictionaryCreateMutable = _setup()


# CFSet emulation functions


def _setup():
    NSSet = _objc.lookUpClass("NSSet")
    NSMutableSet = _objc.lookUpClass("NSMutableSet")

    def CFSetCreate(allocator, values, numvalues, callbacks):
        assert callbacks is None
        return NSSet.alloc().initWithArray_(values[:numvalues])

    def CFSetCreateMutable(allocator, capacity, callbacks):
        assert callbacks is None
        return NSMutableSet.alloc().init()

    return CFSetCreate, CFSetCreateMutable


CFSetCreate, CFSetCreateMutable = _setup()

kCFTypeArrayCallBacks = None
kCFTypeDictionaryKeyCallBacks = None
kCFTypeDictionaryValueCallBacks = None
kCFTypeSetCallBacks = None


#
# Implementation of a number of macro's in the CFBundle API
#


def CFCopyLocalizedString(key, comment):
    return _CF.CFBundleCopyLocalizedString(
        _CF.CFBundleGetMainBundle(), (key), (key), None
    )


def CFCopyLocalizedStringFromTable(key, tbl, comment):
    return _CF.CFBundleCopyLocalizedString(
        _CF.CFBundleGetMainBundle(), (key), (key), (tbl)
    )


def CFCopyLocalizedStringFromTableInBundle(key, tbl, bundle, comment):
    return _CF.CFBundleCopyLocalizedString((bundle), (key), (key), (tbl))


def CFCopyLocalizedStringWithDefaultValue(key, tbl, bundle, value, comment):
    return _CF.CFBundleCopyLocalizedString((bundle), (key), (value), (tbl))


def CFSTR(strval):
    return _objc.lookUpClass("NSString").stringWithString_(strval)
