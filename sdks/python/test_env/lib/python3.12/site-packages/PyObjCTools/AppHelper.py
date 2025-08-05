"""AppKit helpers.

Exported functions:
* runEventLoop - run NSApplicationMain in a safer way
* runConsoleEventLoop - run NSRunLoop.run() in a stoppable manner
* stopEventLoop - stops the event loop or terminates the application
* endSheetMethod - set correct signature for NSSheet callbacks
* callAfter - call a function on the main thread (async)
* callLater - call a function on the main thread after a delay (async)
"""

__all__ = (
    "runEventLoop",
    "runConsoleEventLoop",
    "stopEventLoop",
    "endSheetMethod",
    "callAfter",
    "callLater",
)

import os
import sys
import traceback

import objc
from AppKit import (
    NSApp,
    NSApplicationDidFinishLaunchingNotification,
    NSApplicationMain,
    NSRunAlertPanel,
)
from Foundation import (
    NSAutoreleasePool,
    NSDate,
    NSDefaultRunLoopMode,
    NSLog,
    NSNotificationCenter,
    NSObject,
    NSRunLoop,
    NSThread,
    NSTimer,
)
from objc import super  # noqa: A004


class PyObjCMessageRunner(NSObject):
    """
    Wraps a Python function and its arguments and allows it to be posted to the
    MainThread's `NSRunLoop`.
    """

    def initWithPayload_(self, payload):
        """
        Designated initializer.
        """
        self = super().init()
        if not self:
            return None

        self._payload = payload

        return self

    def callAfter(self):
        """
        Posts a message to the Main thread, to be executed immediately.
        """
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            self.scheduleCallWithDelay_, None, False
        )

    def callLater_(self, delay):
        """
        Posts a message to the Main thread, to be executed after the given
        delay, in seconds.
        """
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            self.scheduleCallWithDelay_, delay, False
        )

    def scheduleCallWithDelay_(self, delay):
        """
        This is run once we're on the Main thread.
        """
        assert NSThread.isMainThread(), "Call is not executing on the Main thread!"

        # There's no delay, just run the call now.
        if not delay:
            self.performCall()
            return

        # There's a delay, schedule it for later.
        self.performSelector_withObject_afterDelay_(self.performCall, None, delay)

    def performCall(self):
        """
        Actually runs the payload.
        """
        assert NSThread.isMainThread(), "Call is not executing on the Main thread!"

        # Unpack the payload.
        (func, args, kwargs) = self._payload

        # Run it.
        func(*args, **kwargs)


def callAfter(func, *args, **kwargs):
    """
    Call a function on the Main thread (async).
    """
    pool = NSAutoreleasePool.alloc().init()
    runner = PyObjCMessageRunner.alloc().initWithPayload_((func, args, kwargs))
    runner.callAfter()
    del runner
    del pool


def callLater(delay, func, *args, **kwargs):
    """
    Call a function on the Main thread after a delay (async).
    """
    pool = NSAutoreleasePool.alloc().init()
    runner = PyObjCMessageRunner.alloc().initWithPayload_((func, args, kwargs))
    runner.callLater_(delay)
    del runner
    del pool


class PyObjCAppHelperApplicationActivator(NSObject):
    def activateNow_(self, aNotification):
        NSApp().activateIgnoringOtherApps_(True)


class PyObjCAppHelperRunLoopStopper(NSObject):
    singletons = {}

    @classmethod
    def currentRunLoopStopper(cls):
        runLoop = NSRunLoop.currentRunLoop()
        return cls.singletons.get(runLoop)

    def init(self):
        self = super().init()
        self.shouldStop = False
        self.isConsole = False
        return self

    def shouldRun(self):
        return not self.shouldStop

    @classmethod
    def addRunLoopStopper_toRunLoop_(cls, runLoopStopper, runLoop):
        if runLoop in cls.singletons:
            raise ValueError("Stopper already registered for this runLoop")
        cls.singletons[runLoop] = runLoopStopper

    @classmethod
    def removeRunLoopStopperFromRunLoop_(cls, runLoop):
        if runLoop not in cls.singletons:
            raise ValueError("Stopper not registered for this runLoop")
        del cls.singletons[runLoop]

    def stop(self):
        self.shouldStop = True
        # this should go away when/if runEventLoop uses
        # runLoop iteration
        if not self.isConsole:
            if NSApp() is not None:
                NSApp().terminate_(self)

    def performStop_(self, sender):
        self.stop()


def stopEventLoop():
    """
    Stop the current event loop if possible
    returns True if it expects that it was successful, False otherwise
    """
    stopper = PyObjCAppHelperRunLoopStopper.currentRunLoopStopper()
    if stopper is None:
        if NSApp() is not None:
            NSApp().terminate_(None)
            return True
        return False
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.0, stopper, "performStop:", None, False
    )
    return True


def endSheetMethod(meth):
    """
    Return a selector that can be used as the delegate callback for
    sheet methods
    """
    return objc.selector(
        meth, signature=b"v@:@" + objc._C_NSInteger + objc._C_NSInteger
    )


def unexpectedErrorAlertPanel():
    exceptionInfo = traceback.format_exception_only(*sys.exc_info()[:2])[0].strip()
    return NSRunAlertPanel(
        "An unexpected error has occurred",
        "%@",
        "Continue",
        "Quit",
        None,
        "(%s)" % exceptionInfo,
    )


def unexpectedErrorAlertPdb():
    import pdb

    traceback.print_exc()
    pdb.post_mortem(sys.exc_info()[2])
    return True


def machInterrupt(signum):
    stopper = PyObjCAppHelperRunLoopStopper.currentRunLoopStopper()
    if stopper is not None:
        stopper.stop()
    elif NSApp() is not None:
        NSApp().terminate_(None)
    else:
        import os

        os._exit(1)


def installMachInterrupt():
    import signal
    from PyObjCTools import MachSignals

    MachSignals.signal(signal.SIGINT, machInterrupt)


def runConsoleEventLoop(
    argv=None, installInterrupt=False, mode=NSDefaultRunLoopMode, maxTimeout=3.0
):
    if argv is None:
        argv = sys.argv
    if installInterrupt:
        installMachInterrupt()
    runLoop = NSRunLoop.currentRunLoop()
    stopper = PyObjCAppHelperRunLoopStopper.alloc().init()
    stopper.isConsole = True
    PyObjCAppHelperRunLoopStopper.addRunLoopStopper_toRunLoop_(stopper, runLoop)
    try:
        while stopper.shouldRun():
            nextfire = runLoop.limitDateForMode_(mode)
            if not stopper.shouldRun():
                break

            soon = NSDate.dateWithTimeIntervalSinceNow_(maxTimeout)
            if nextfire is not None:
                nextfire = soon.earlierDate_(nextfire)
            if not runLoop.runMode_beforeDate_(mode, nextfire):
                stopper.stop()

    finally:
        PyObjCAppHelperRunLoopStopper.removeRunLoopStopperFromRunLoop_(runLoop)


RAISETHESE = (SystemExit, MemoryError, KeyboardInterrupt)


def runEventLoop(
    argv=None,
    unexpectedErrorAlert=None,
    installInterrupt=None,
    pdb=None,
    main=NSApplicationMain,
):
    """Run the event loop, ask the user if we should continue if an
    exception is caught. Use this function instead of NSApplicationMain().
    """
    if argv is None:
        argv = sys.argv

    if pdb is None:
        pdb = "USE_PDB" in os.environ

    if pdb:
        from PyObjCTools import Debugging

        Debugging.installVerboseExceptionHandler()
        # bring it to the front, starting from terminal
        # often won't
        activator = PyObjCAppHelperApplicationActivator.alloc().init()
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            activator, "activateNow:", NSApplicationDidFinishLaunchingNotification, None
        )
    else:
        Debugging = None

    if installInterrupt is None and pdb:
        installInterrupt = True

    if unexpectedErrorAlert is None:
        if pdb:
            unexpectedErrorAlert = unexpectedErrorAlertPdb
        else:
            unexpectedErrorAlert = unexpectedErrorAlertPanel

    runLoop = NSRunLoop.currentRunLoop()
    stopper = PyObjCAppHelperRunLoopStopper.alloc().init()
    PyObjCAppHelperRunLoopStopper.addRunLoopStopper_toRunLoop_(stopper, runLoop)

    firstRun = NSApp() is None
    try:
        while stopper.shouldRun():
            try:
                if firstRun:
                    firstRun = False
                    if installInterrupt:
                        installMachInterrupt()
                    main(argv)
                else:
                    NSApp().run()
            except RAISETHESE:
                traceback.print_exc()
                break
            except:  # noqa: E722, B001
                exctype, e, tb = sys.exc_info()
                if isinstance(e, objc.error):
                    error_str = str(e)

                    NSLog("%@", error_str)
                elif not unexpectedErrorAlert():
                    NSLog("%@", "An exception has occurred:")
                    traceback.print_exc()
                    sys.exit(0)
                else:
                    NSLog("%@", "An exception has occurred:")
                    traceback.print_exc()
            else:
                break

    finally:
        if Debugging is not None:
            Debugging.removeExceptionHandler()
        PyObjCAppHelperRunLoopStopper.removeRunLoopStopperFromRunLoop_(runLoop)
