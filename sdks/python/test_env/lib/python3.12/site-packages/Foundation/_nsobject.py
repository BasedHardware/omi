"""
Define a category on NSObject with some useful methods.
"""

import sys

import objc

if sys.version_info[0] == 2:

    def _str(v):
        return v

    exec(
        """\
def _raise(exc_type, exc_value, exc_trace):
    raise exc_type, exc_value, exc_trace
"""
    )
else:

    def _str(v):
        if isinstance(v, str):
            return v
        return v.decode("ascii")

    def _raise(exc_type, exc_value, exc_trace):
        raise exc_type(exc_value).with_traceback(exc_trace)


NSObject = objc.lookUpClass("NSObject")


class NSObject(objc.Category(NSObject)):
    @objc.namedSelector(b"_pyobjc_performOnThread:")
    def _pyobjc_performOnThread_(self, callinfo):
        try:
            sel, arg = callinfo
            m = getattr(self, _str(sel))
            m(arg)
        except:  # noqa: E722, B001
            import traceback

            traceback.print_exc(file=sys.stderr)

    @objc.namedSelector(b"_pyobjc_performOnThreadWithResult:")
    def _pyobjc_performOnThreadWithResult_(self, callinfo):
        try:
            sel, arg, result = callinfo
            m = getattr(self, _str(sel))
            r = m(arg)
            result.append((True, r))
        except:  # noqa: E722, B001
            result.append((False, sys.exc_info()))

    if hasattr(NSObject, "performSelector_onThread_withObject_waitUntilDone_"):

        @objc.namedSelector(
            b"pyobjc_performSelector:onThread:withObject:waitUntilDone:"
        )
        def pyobjc_performSelector_onThread_withObject_waitUntilDone_(
            self, aSelector, thread, arg, wait
        ):
            """
            A version of performSelector:onThread:withObject:waitUntilDone: that
            will log exceptions in the called method (instead of aborting the
            NSRunLoop on the other thread).
            """
            self.performSelector_onThread_withObject_waitUntilDone_(
                b"_pyobjc_performOnThread:", thread, (aSelector, arg), wait
            )

        @objc.namedSelector(
            b"pyobjc_performSelector:onThread:withObject:waitUntilDone:modes:"
        )
        def pyobjc_performSelector_onThread_withObject_waitUntilDone_modes_(
            self, aSelector, thread, arg, wait, modes
        ):
            """
            A version of performSelector:onThread:withObject:waitUntilDone:modes:
            that will log exceptions in the called method (instead of aborting the
            NSRunLoop on the other thread).
            """
            self.performSelector_onThread_withObject_waitUntilDone_modes_(
                b"_pyobjc_performOnThread:", thread, (aSelector, arg), wait, modes
            )

    @objc.namedSelector(b"pyobjc_performSelector:withObject:afterDelay:")
    def pyobjc_performSelector_withObject_afterDelay_(self, aSelector, arg, delay):
        """
        A version of performSelector:withObject:afterDelay:
        that will log exceptions in the called method (instead of aborting the
        NSRunLoop).
        """
        self.performSelector_withObject_afterDelay_(
            b"_pyobjc_performOnThread:", (aSelector, arg), delay
        )

    @objc.namedSelector(b"pyobjc_performSelector:withObject:afterDelay:inModes:")
    def pyobjc_performSelector_withObject_afterDelay_inModes_(
        self, aSelector, arg, delay, modes
    ):
        """
        A version of performSelector:withObject:afterDelay:inModes:
        that will log exceptions in the called method (instead of aborting the
        NSRunLoop).
        """
        self.performSelector_withObject_afterDelay_inModes_(
            b"_pyobjc_performOnThread:", (aSelector, arg), delay, modes
        )

    if hasattr(NSObject, "performSelectorInBackground_withObject_"):

        @objc.namedSelector(b"pyobjc_performSelectorInBackground:withObject:")
        def pyobjc_performSelectorInBackground_withObject_(self, aSelector, arg):
            """
            A version of performSelectorInBackground:withObject:
            that will log exceptions in the called method (instead of aborting the
            NSRunLoop).
            """
            self.performSelectorInBackground_withObject_(
                b"_pyobjc_performOnThread:", (aSelector, arg)
            )

    @objc.namedSelector(b"pyobjc_performSelectorOnMainThread:withObject:waitUntilDone:")
    def pyobjc_performSelectorOnMainThread_withObject_waitUntilDone_(
        self, aSelector, arg, wait
    ):
        """
        A version of performSelectorOnMainThread:withObject:waitUntilDone:
        that will log exceptions in the called method (instead of aborting the
        NSRunLoop in the main thread).
        """
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            b"_pyobjc_performOnThread:", (aSelector, arg), wait
        )

    @objc.namedSelector(
        b"pyobjc_performSelectorOnMainThread:withObject:waitUntilDone:modes:"
    )
    def pyobjc_performSelectorOnMainThread_withObject_waitUntilDone_modes_(
        self, aSelector, arg, wait, modes
    ):
        """
        A version of performSelectorOnMainThread:withObject:waitUntilDone:modes:
        that will log exceptions in the called method (instead of aborting the
        NSRunLoop in the main thread).
        """
        self.performSelectorOnMainThread_withObject_waitUntilDone_modes_(
            b"_pyobjc_performOnThread:", (aSelector, arg), wait, modes
        )

    # And some a some versions that return results

    @objc.namedSelector(b"pyobjc_performSelectorOnMainThread:withObject:modes:")
    def pyobjc_performSelectorOnMainThread_withObject_modes_(
        self, aSelector, arg, modes
    ):
        """
        Simular to performSelectorOnMainThread:withObject:waitUntilDone:modes:,
        but:

        - always waits until done
        - returns the return value of the called method
        - if the called method raises an exception, this will raise the same
           exception
        """
        result = []
        self.performSelectorOnMainThread_withObject_waitUntilDone_modes_(
            b"_pyobjc_performOnThreadWithResult:", (aSelector, arg, result), True, modes
        )
        isOK, result = result[0]

        if isOK:
            return result
        else:
            exc_type, exc_value, exc_trace = result
            _raise(exc_type, exc_value, exc_trace)

    @objc.namedSelector(b"pyobjc_performSelectorOnMainThread:withObject:")
    def pyobjc_performSelectorOnMainThread_withObject_(self, aSelector, arg):
        result = []
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            b"_pyobjc_performOnThreadWithResult:", (aSelector, arg, result), True
        )
        isOK, result = result[0]

        if isOK:
            return result
        else:
            exc_type, exc_value, exc_trace = result
            _raise(exc_type, exc_value, exc_trace)

    if hasattr(NSObject, "performSelector_onThread_withObject_waitUntilDone_"):
        # These methods require Leopard, don't define them if the
        # platform functionality isn't present.

        @objc.namedSelector(b"pyobjc_performSelector:onThread:withObject:modes:")
        def pyobjc_performSelector_onThread_withObject_modes_(
            self, aSelector, thread, arg, modes
        ):
            result = []
            self.performSelector_onThread_withObject_waitUntilDone_modes_(
                b"_pyobjc_performOnThreadWithResult:",
                thread,
                (aSelector, arg, result),
                True,
                modes,
            )
            isOK, result = result[0]

            if isOK:
                return result
            else:
                exc_type, exc_value, exc_trace = result
                _raise(exc_type, exc_value, exc_trace)

        @objc.namedSelector(b"pyobjc_performSelector:onThread:withObject:")
        def pyobjc_performSelector_onThread_withObject_(self, aSelector, thread, arg):
            result = []
            self.performSelector_onThread_withObject_waitUntilDone_(
                b"_pyobjc_performOnThreadWithResult:",
                thread,
                (aSelector, arg, result),
                True,
            )
            isOK, result = result[0]

            if isOK:
                return result
            else:
                exc_type, exc_value, exc_trace = result
                _raise(exc_type, exc_value, exc_trace)


del NSObject
