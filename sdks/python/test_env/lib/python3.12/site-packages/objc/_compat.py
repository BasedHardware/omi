import warnings

from objc import options as _options


def setVerbose(value):
    warnings.warn("Set objc.options.verbose instead", DeprecationWarning, stacklevel=2)
    _options.verbose = bool(value)


def getVerbose():
    warnings.warn("Read objc.options.verbose instead", DeprecationWarning, stacklevel=2)
    return _options.verbose


def setUseKVOForSetattr(value):
    warnings.warn("Set objc.options.use_kvo instead", DeprecationWarning, stacklevel=2)
    _options.use_kvo = bool(value)


def getUseKVOForSetattr():
    warnings.warn("Read objc.options.use_kvo instead", DeprecationWarning, stacklevel=2)
    return _options.use_kvo


def allocateBuffer(length):
    """Allocate a read/write buffer of memory of the given size."""
    if not isinstance(length, int) or length <= 0:
        raise TypeError("length must be a positive integer")

    warnings.warn("Use bytearray instead", DeprecationWarning, stacklevel=2)

    return bytearray(length)
