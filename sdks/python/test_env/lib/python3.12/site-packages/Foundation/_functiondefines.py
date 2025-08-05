"""
Port of "function defines".
"""

import Foundation as _Foundation


def NSLocalizedString(key, comment):
    return _Foundation.NSBundle.mainBundle().localizedStringForKey_value_table_(
        key, "", None
    )


def NSLocalizedStringFromTable(key, tbl, comment):
    return _Foundation.NSBundle.mainBundle().localizedStringForKey_value_table_(
        key, "", tbl
    )


def NSLocalizedStringFromTableInBundle(key, tbl, bundle, comment):
    return bundle.localizedStringForKey_value_table_(key, "", tbl)


def NSLocalizedStringWithDefaultValue(key, tbl, bundle, val, comment):
    return bundle.localizedStringForKey_value_table_(key, val, tbl)


def NSLocalizedAttributedString(key, comment):
    return (
        _Foundation.NSBundle.mainBundle().localizedAttributedStringForKey_value_table_(
            key, "", None
        )
    )


def NSLocalizedAttributedStringFromTable(key, tbl, comment):
    return _Foundation.NSBundle.mainBundle.localizedAttributedStringForKey_value_table_(
        key, "", tbl
    )


def NSLocalizedAttributedStringFromTableInBundle(key, tbl, bundle, comment):
    return bundle.localizedAttributedStringForKey_value_table_(key, "", tbl)


def NSLocalizedAttributedStringWithDefaultValue(key, tbl, bundle, val, comment):
    return bundle.localizedAttributedStringForKey_value_table_(key, val, tbl)


def MIN(a, b):
    if a < b:
        return a
    else:
        return b


def MAX(a, b):
    if a < b:
        return b
    else:
        return a


ABS = abs
