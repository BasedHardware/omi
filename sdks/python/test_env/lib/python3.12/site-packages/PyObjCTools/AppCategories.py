"""
A number of useful categories on AppKit classes
"""

__all__ = ()
import objc
from AppKit import NSAnimationContext, NSGraphicsContext


class _ctxHelper:
    def __enter__(self):
        NSGraphicsContext.saveGraphicsState()

    def __exit__(self, exc_type, exc_value, exc_tb):
        NSGraphicsContext.restoreGraphicsState()
        return False


class NSGraphicsContext(objc.Category(NSGraphicsContext)):
    @classmethod
    def savedGraphicsState(self):
        return _ctxHelper()


@objc.python_method
def __enter__(cls):
    cls.beginGrouping()


@objc.python_method
def __exit__(cls, exc_type, exc_value, exc_tb):
    cls.endGrouping()


# Cannot use a category here because these special methods
# must be defined on the metaclass.
type(NSAnimationContext).__enter__ = __enter__
type(NSAnimationContext).__exit__ = __exit__
