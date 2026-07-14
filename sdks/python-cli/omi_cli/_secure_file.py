"""Create credential files with owner-only access on POSIX and Windows."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

# Protected DACL: FILE_ALL_ACCESS for the file owner, with no inherited ACEs.
_WINDOWS_OWNER_ONLY_DACL = "D:P(A;;FA;;;OW)"
_SDDL_REVISION_1 = 1
_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_READ_CONTROL = 0x00020000
_GENERIC_WRITE = 0x40000000
_CREATE_NEW = 1
_FILE_ATTRIBUTE_NORMAL = 0x80
_ERROR_FILE_EXISTS = 80
_ERROR_ALREADY_EXISTS = 183


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


def open_owner_only(path: Path) -> int:
    """Create *path* exclusively and return a writable, owner-only descriptor."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if sys.platform != "win32":
        return os.open(path, flags, 0o600)
    return _open_owner_only_windows(path)


if sys.platform == "win32":
    import msvcrt

    def _open_owner_only_windows(path: Path) -> int:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        convert_sddl = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert_sddl.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.ULONG),
        ]
        convert_sddl.restype = wintypes.BOOL

        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(_SecurityAttributes),
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE

        local_free = kernel32.LocalFree
        local_free.argtypes = [wintypes.HLOCAL]
        local_free.restype = wintypes.HLOCAL

        security_descriptor = wintypes.LPVOID()
        descriptor_size = wintypes.ULONG()
        if not convert_sddl(
            _WINDOWS_OWNER_ONLY_DACL,
            _SDDL_REVISION_1,
            ctypes.byref(security_descriptor),
            ctypes.byref(descriptor_size),
        ):
            error = ctypes.get_last_error()
            raise OSError(error, "Windows could not build an owner-only security descriptor", str(path))

        try:
            attributes = _SecurityAttributes(
                ctypes.sizeof(_SecurityAttributes),
                security_descriptor,
                False,
            )
            # READ_CONTROL lets us verify the DACL before writing any credential.
            handle = create_file(
                str(path),
                _GENERIC_WRITE | _READ_CONTROL,
                0,
                ctypes.byref(attributes),
                _CREATE_NEW,
                _FILE_ATTRIBUTE_NORMAL,
                None,
            )
            create_error = ctypes.get_last_error() if handle == wintypes.HANDLE(-1).value else 0
        finally:
            local_free(security_descriptor)

        if handle == wintypes.HANDLE(-1).value:
            error = create_error
            if error in {_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS}:
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(path))
            raise OSError(error, "Windows could not create the owner-only file", str(path))

        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        try:
            if _windows_dacl_sddl(handle) != _WINDOWS_OWNER_ONLY_DACL:
                raise PermissionError(errno.EACCES, "Windows did not enforce owner-only file permissions", str(path))
            descriptor_flags = os.O_WRONLY | getattr(os, "O_BINARY", 0)
            return msvcrt.open_osfhandle(handle, descriptor_flags)
        except BaseException:
            close_handle(handle)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _windows_dacl_sddl(handle: int, *, _advapi32: Any = None, _kernel32: Any = None) -> str:
        """Return the protected DACL for a Windows file handle as stable SDDL."""
        advapi32 = _advapi32 or ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = _kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)

        get_security_info = advapi32.GetSecurityInfo
        get_security_info.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
        ]
        get_security_info.restype = wintypes.DWORD

        convert_sddl = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
        convert_sddl.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.ULONG),
        ]
        convert_sddl.restype = wintypes.BOOL

        local_free = kernel32.LocalFree
        local_free.argtypes = [wintypes.HLOCAL]
        local_free.restype = wintypes.HLOCAL

        security_descriptor = wintypes.LPVOID()
        dacl = wintypes.LPVOID()
        result = get_security_info(
            handle,
            _SE_FILE_OBJECT,
            _DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(security_descriptor),
        )
        if result != 0:
            raise OSError(result, "Windows could not read the file security descriptor")

        try:
            sddl = wintypes.LPWSTR()
            sddl_length = wintypes.ULONG()
            if not convert_sddl(
                security_descriptor,
                _SDDL_REVISION_1,
                _DACL_SECURITY_INFORMATION,
                ctypes.byref(sddl),
                ctypes.byref(sddl_length),
            ):
                error = ctypes.get_last_error()
                raise OSError(error, "Windows could not verify the owner-only DACL")
            try:
                return sddl.value or ""
            finally:
                local_free(sddl)
        finally:
            local_free(security_descriptor)

else:

    def _open_owner_only_windows(path: Path) -> int:
        raise OSError(errno.ENOSYS, "Windows owner-only file creation is unavailable", str(path))

    def _windows_dacl_sddl(handle: int, *, _advapi32: Any = None, _kernel32: Any = None) -> str:
        raise OSError(errno.ENOSYS, "Windows DACL inspection is unavailable")
