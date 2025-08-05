"""
Support for @synchronized blocks

The python class object_lock is a contextmanager for with statements that
can also be used manually.
"""

import objc as _objc


class object_lock:
    """
    A context manager that implements the same feature as
    @synchronized statements in Objective-C. Locking can also
    be done manually using the ``lock`` and ``unlock`` methods.

    The mutex for object ``anObject`` is represented by
    ``objc.object_lock(anObject)``.

    Usage:

        with object_lock(anObject):
            ...
    """

    def __init__(self, value):
        self.__value = value

    def __enter__(self):
        _objc._objc_sync_enter(self.__value)

    def __exit__(self, exc_type, value, tp):
        _objc._objc_sync_exit(self.__value)

    def lock(self):
        _objc._objc_sync_enter(self.__value)

    def unlock(self):
        _objc._objc_sync_exit(self.__value)
