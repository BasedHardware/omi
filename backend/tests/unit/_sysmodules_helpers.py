"""Centralized sys.modules stub install/restore helper.

Used by conftest.py hooks and per-file module-scoped fixtures
to manage stub lifecycle with proper parent-attribute teardown.
"""

import sys
from contextlib import contextmanager

_SENTINEL = object()


@contextmanager
def stub_modules(stub_names):
    """Install/restore sys.modules stubs with proper parent-attr teardown.

    Use in module-scoped autouse fixtures inside test files that do
    module-level stubbing::

        from tests.unit._sysmodules_helpers import stub_modules

        _STUB_NAMES = ["database", "database._client", ...]
        _snap = {k: sys.modules[k] for k in _STUB_NAMES if k in sys.modules}

        @pytest.fixture(autouse=True, scope="module")
        def _reinstall_stubs():
            with stub_modules(_STUB_NAMES) as install:
                install(_snap)
                yield
    """
    prev_modules = {k: sys.modules.get(k) for k in stub_names}
    prev_attrs = {}
    for k in stub_names:
        if '.' in k:
            parent_name, attr_name = k.rsplit('.', 1)
            parent = sys.modules.get(parent_name)
            if parent is not None:
                prev_attrs[k] = (parent, attr_name, getattr(parent, attr_name, _SENTINEL))

    def _install(snapshot):
        for k, mod in snapshot.items():
            sys.modules[k] = mod
            if '.' in k:
                parent_name, attr_name = k.rsplit('.', 1)
                parent = sys.modules.get(parent_name)
                if parent is not None:
                    setattr(parent, attr_name, mod)

    try:
        yield _install
    finally:
        for k, old in prev_modules.items():
            if old is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = old
        for k, (parent, attr_name, orig_val) in prev_attrs.items():
            if orig_val is _SENTINEL:
                try:
                    delattr(parent, attr_name)
                except AttributeError:
                    pass
            else:
                setattr(parent, attr_name, orig_val)
