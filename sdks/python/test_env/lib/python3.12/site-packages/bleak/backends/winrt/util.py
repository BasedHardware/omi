import asyncio
import ctypes
import sys
from ctypes import wintypes
from enum import IntEnum
from typing import Tuple

from ...exc import BleakError

if sys.version_info < (3, 11):
    from async_timeout import timeout as async_timeout
else:
    from asyncio import timeout as async_timeout


def _check_result(result, func, args):
    if not result:
        raise ctypes.WinError()

    return args


def _check_hresult(result, func, args):
    if result:
        raise ctypes.WinError(result)

    return args


# not defined in wintypes
_UINT_PTR = wintypes.WPARAM

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nc-winuser-timerproc
_TIMERPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HWND, _UINT_PTR, wintypes.UINT, wintypes.DWORD
)

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-settimer
_SET_TIMER_PROTOTYPE = ctypes.WINFUNCTYPE(
    _UINT_PTR, wintypes.HWND, _UINT_PTR, wintypes.UINT, _TIMERPROC
)
_SET_TIMER_PARAM_FLAGS = (
    (1, "hwnd", None),
    (1, "nidevent"),
    (1, "uelapse"),
    (1, "lptimerfunc", None),
)
_SetTimer = _SET_TIMER_PROTOTYPE(
    ("SetTimer", ctypes.windll.user32), _SET_TIMER_PARAM_FLAGS
)
_SetTimer.errcheck = _check_result

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-killtimer
_KILL_TIMER_PROTOTYPE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, _UINT_PTR)
_KILL_TIMER_PARAM_FLAGS = (
    (1, "hwnd", None),
    (1, "uidevent"),
)
_KillTimer = _KILL_TIMER_PROTOTYPE(
    ("KillTimer", ctypes.windll.user32), _KILL_TIMER_PARAM_FLAGS
)

# https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cogetapartmenttype
_CO_GET_APARTMENT_TYPE_PROTOTYPE = ctypes.WINFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
)
_CO_GET_APARTMENT_TYPE_PARAM_FLAGS = (
    (1, "papttype", None),
    (1, "paptqualifier", None),
)
_CoGetApartmentType = _CO_GET_APARTMENT_TYPE_PROTOTYPE(
    ("CoGetApartmentType", ctypes.windll.ole32), _CO_GET_APARTMENT_TYPE_PARAM_FLAGS
)
_CoGetApartmentType.errcheck = _check_hresult

_CO_E_NOTINITIALIZED = -2147221008


# https://learn.microsoft.com/en-us/windows/win32/api/objidl/ne-objidl-apttype
class _AptType(IntEnum):
    CURRENT = -1
    STA = 0
    MTA = 1
    NA = 2
    MAIN_STA = 3


# https://learn.microsoft.com/en-us/windows/win32/api/objidl/ne-objidl-apttypequalifier
class _AptQualifierType(IntEnum):
    NONE = 0
    IMPLICIT_MTA = 1
    NA_ON_MTA = 2
    NA_ON_STA = 3
    NA_ON_IMPLICIT_STA = 4
    NA_ON_MAIN_STA = 5
    APPLICATION_STA = 6
    RESERVED_1 = 7


def _get_apartment_type() -> Tuple[_AptType, _AptQualifierType]:
    """
    Calls CoGetApartmentType to get the current apartment type and qualifier.

    Returns:
        The current apartment type and qualifier.
    Raises:
        OSError: If the call to CoGetApartmentType fails.
    """
    api_type = ctypes.c_int()
    api_type_qualifier = ctypes.c_int()
    _CoGetApartmentType(ctypes.byref(api_type), ctypes.byref(api_type_qualifier))
    return _AptType(api_type.value), _AptQualifierType(api_type_qualifier.value)


async def assert_mta() -> None:
    """
    Asserts that the current apartment type is MTA.

    Raises:
        BleakError:
            If the current apartment type is not MTA and there is no Windows
            message loop running.

    .. versionadded:: 0.22

    .. versionchanged:: 0.22.2

        Function is now async and will not raise if the current apartment type
        is STA and the Windows message loop is running.
    """
    if hasattr(allow_sta, "_allowed"):
        return

    try:
        apt_type, _ = _get_apartment_type()
    except OSError as e:
        # All is OK if not initialized yet. WinRT will initialize it.
        if e.winerror == _CO_E_NOTINITIALIZED:
            return

        raise

    if apt_type == _AptType.MTA:
        # if we get here, WinRT probably set the apartment type to MTA and all
        # is well, we don't need to check again
        setattr(allow_sta, "_allowed", True)
        return

    event = asyncio.Event()

    def wait_event(*_):
        event.set()

    # have to keep a reference to the callback or it will be garbage collected
    # before it is called
    callback = _TIMERPROC(wait_event)

    # set a timer to see if we get a callback to ensure the windows event loop
    # is running
    timer = _SetTimer(None, 1, 0, callback)

    try:
        async with async_timeout(0.5):
            await event.wait()
    except asyncio.TimeoutError:
        raise BleakError(
            "Thread is configured for Windows GUI but callbacks are not working."
            + (
                " Suspect unwanted side effects from importing 'pythoncom'."
                if "pythoncom" in sys.modules
                else ""
            )
        )
    else:
        # if the windows event loop is running, we assume it is going to keep
        # running and we don't need to check again
        setattr(allow_sta, "_allowed", True)
    finally:
        _KillTimer(None, timer)


def allow_sta():
    """
    Suppress check for MTA thread type and allow STA.

    Bleak will hang forever if the current thread is not MTA - unless there is
    a Windows event loop running that is properly integrated with asyncio in
    Python.

    If your program meets that condition, you must call this function do disable
    the check for MTA. If your program doesn't have a graphical user interface
    you probably shouldn't call this function. and use ``uninitialize_sta()``
    instead.

    .. versionadded:: 0.22.1
    """
    allow_sta._allowed = True


def uninitialize_sta():
    """
    Uninitialize the COM library on the current thread if it was not initialized
    as MTA.

    This is intended to undo the implicit initialization of the COM library as STA
    by packages like pywin32.

    It should be called as early as possible in your application after the
    offending package has been imported.

    .. versionadded:: 0.22
    """

    try:
        _get_apartment_type()
    except OSError as e:
        # All is OK if not initialized yet. WinRT will initialize it.
        if e.winerror == _CO_E_NOTINITIALIZED:
            return
    else:
        ctypes.windll.ole32.CoUninitialize()
