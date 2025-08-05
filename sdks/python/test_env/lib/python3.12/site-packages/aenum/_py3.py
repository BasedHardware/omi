from inspect import getfullargspec as _getfullargspec

__all__ = [
        'getargspec', 'raise_with_traceback', 'raise_from_none',
        ]

def getargspec(method):
    args, varargs, keywords, defaults, _, _, _ = _getfullargspec(method)
    return args, varargs, keywords, defaults

def raise_with_traceback(exc, tb):
    raise exc.with_traceback(tb)

def raise_from_none(exc):
    raise exc from None

