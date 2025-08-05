"""
dyld emulation
"""

__all__ = [
    "dyld_framework",
    "dyld_library",
    "dyld_find",
    "pathForFramework",
    "infoForFramework",
]

import os

from objc._framework import infoForFramework
from objc._objc import _dyld_shared_cache_contains_path

# These are the defaults as per man dyld(1)
#
DEFAULT_FRAMEWORK_FALLBACK = ":".join(
    [
        os.path.expanduser("~/Library/Frameworks"),
        "/Library/Frameworks",
        "/Network/Library/Frameworks",
        "/System/Library/Frameworks",
    ]
)

DEFAULT_LIBRARY_FALLBACK = ":".join(
    [os.path.expanduser("~/lib"), "/usr/local/lib", "/lib", "/usr/lib"]
)


def ensure_unicode(s):
    """Not all of PyObjC understands unicode paths very well yet"""
    if isinstance(s, bytes):
        return s.decode("utf-8")
    return s


def inject_suffixes(iterator):
    suffix = ensure_unicode(os.environ.get("DYLD_IMAGE_SUFFIX", None))
    if suffix is None:
        return iterator

    def _inject(iterator=iterator, suffix=suffix):
        for path in iterator:
            if path.endswith(".dylib"):
                yield path[:-6] + suffix + ".dylib"
            else:
                yield path + suffix
            yield path

    return _inject()


def dyld_framework(filename, framework_name, version=None):
    """Find a framework using dyld semantics"""
    filename = ensure_unicode(filename)
    framework_name = ensure_unicode(framework_name)
    version = ensure_unicode(version)

    def _search():
        spath = ensure_unicode(os.environ.get("DYLD_FRAMEWORK_PATH", None))
        if spath is not None:
            for path in spath.split(":"):
                if version:
                    yield os.path.join(
                        path,
                        framework_name + ".framework",
                        "Versions",
                        version,
                        framework_name,
                    )
                else:
                    yield os.path.join(
                        path, framework_name + ".framework", framework_name
                    )
        yield filename
        spath = ensure_unicode(
            os.environ.get("DYLD_FALLBACK_FRAMEWORK_PATH", DEFAULT_FRAMEWORK_FALLBACK)
        )
        for path in spath.split(":"):
            if version:
                yield os.path.join(
                    path,
                    framework_name + ".framework",
                    "Versions",
                    version,
                    framework_name,
                )
            else:
                yield os.path.join(path, framework_name + ".framework", framework_name)

    for f in inject_suffixes(_search()):
        if _dyld_shared_cache_contains_path(f):
            return f

        if os.path.exists(f):
            return f
    # raise ..
    raise ImportError(f"Framework {framework_name} could not be found")


def dyld_library(filename, libname):
    """Find a dylib using dyld semantics"""
    filename = ensure_unicode(filename)
    libname = ensure_unicode(libname)

    def _search():
        spath = ensure_unicode(os.environ.get("DYLD_LIBRARY_PATH", None))
        if spath is not None:
            for path in spath.split(":"):
                yield os.path.join(path, libname)
        yield filename
        spath = ensure_unicode(
            os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", DEFAULT_LIBRARY_FALLBACK)
        )
        for path in spath.split(":"):
            yield os.path.join(path, libname)

    for f in inject_suffixes(_search()):
        if _dyld_shared_cache_contains_path(f):
            return f
        if os.path.exists(f):
            return f
    raise ValueError(f"dylib {filename} could not be found")


def dyld_find(filename):
    """Generic way to locate a dyld framework or dyld"""
    filename = os.path.realpath(filename)
    res = infoForFramework(filename)
    if res:
        framework_loc, framework_name, version = res
        return dyld_framework(filename, framework_name, version)
    else:
        return dyld_library(filename, os.path.basename(filename))


def pathForFramework(path):
    fpath, name, version = infoForFramework(dyld_find(path))
    return os.path.join(fpath, name + ".framework")
