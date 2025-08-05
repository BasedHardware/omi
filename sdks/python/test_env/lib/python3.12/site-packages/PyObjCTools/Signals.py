"""Signals.py -- dump a python stacktrace if something bad happens.

          DO NOT USE THIS MODULE IN PRODUCTION CODE

This module has two functions in its public API:

- dumpStackOnFatalSignal()
  This function will install signal handlers that print a stacktrace and
  then reraise the signal.

- resetFatalSignals()
  Restores the signal handlers to the state they had before the call to
  dumpStackOnFatalSignal.

This module is not designed to provide fine grained control over signal
handling. Nor is it intended to be terribly robust. It may give useful
information when your program gets unexpected signals, but it might just
as easily cause a crash when such a signal gets in.

          DO NOT USE THIS MODULE IN PRODUCTION CODE
"""

import os
import signal
import traceback
import warnings
import sys

__all__ = ["dumpStackOnFatalSignal", "resetFatalSignals"]

warnings.warn(
    "PyObjCTools.Signals is deprecated and will be removed in PyObjC 9",
    DeprecationWarning,
    stacklevel=1,
)


originalHandlers = None


def dumpHandler(signum, frame):
    """
    the signal handler used in this module: print a stacktrace and
    then re-raise the signal
    """
    resetFatalSignals()
    print("*** Handling fatal signal '%d'." % signum, file=sys.stderr)
    traceback.print_stack(frame)
    print("*** Restored handlers and resignaling.", file=sys.stderr)
    os.kill(os.getpid(), signum)


def installHandler(sig):
    """
    Install our signal handler for a signal. The original handler
    is saved in 'originalHandlers'.
    """
    originalHandlers[sig] = signal.signal(sig, dumpHandler)


def dumpStackOnFatalSignal():
    """
    Install signal handlers that might print a useful stack trace when
    this process receives a fatal signal.

    NOTE: See module docstring
    """

    global originalHandlers
    if not originalHandlers:
        originalHandlers = {}
        installHandler(signal.SIGQUIT)
        installHandler(signal.SIGILL)
        installHandler(signal.SIGTRAP)
        installHandler(signal.SIGABRT)
        installHandler(signal.SIGEMT)
        installHandler(signal.SIGFPE)
        installHandler(signal.SIGBUS)
        installHandler(signal.SIGSEGV)
        installHandler(signal.SIGSYS)


def resetFatalSignals():
    """
    Restore the original signal handlers
    """
    global originalHandlers
    if originalHandlers:
        for sig in originalHandlers:
            signal.signal(sig, originalHandlers[sig])
        originalHandlers = None
