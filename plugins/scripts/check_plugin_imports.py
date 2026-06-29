#!/usr/bin/env python3
"""Import each Python plugin app and build OpenAPI schemas when dependencies are present."""

import importlib
import os
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SDK_SRC = PLUGINS / "omi-plugin-sdk" / "src"


def main() -> int:
    blockers: List[Tuple[str, str]] = []
    checked = 0
    plugin_roots = [path.resolve() for path in PLUGINS.glob("omi-*-app")]

    for main_py in sorted(PLUGINS.glob("omi-*-app/main.py")):
        app_dir = main_py.parent
        module_name = "main"
        checked += 1
        sys.path[:0] = [str(app_dir), str(SDK_SRC)]
        old_cwd = Path.cwd()
        os.chdir(app_dir)
        try:
            _purge_plugin_modules(plugin_roots)
            module = importlib.import_module(module_name)
            app = getattr(module, "app", None)
            if app is None:
                blockers.append((app_dir.name, "main.py imported but has no app attribute"))
                continue
            app.openapi()
        except ModuleNotFoundError as exc:
            blockers.append((app_dir.name, f"missing dependency: {exc.name}"))
        except Exception as exc:  # noqa: BLE001 - smoke script must report import blockers without hiding later apps.
            blockers.append((app_dir.name, f"{type(exc).__name__}: {exc}"))
        finally:
            os.chdir(old_cwd)
            for path in (str(app_dir), str(SDK_SRC)):
                try:
                    sys.path.remove(path)
                except ValueError:
                    pass

    print(f"checked={checked}")
    if blockers:
        print("blockers:")
        for app, reason in blockers:
            print(f"- {app}: {reason}")
        return 1
    print("all plugin apps imported and generated OpenAPI")
    return 0


def _purge_plugin_modules(plugin_roots: List[Path]) -> None:
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            resolved = Path(module_file).resolve()
        except OSError:
            continue
        if any(_is_relative_to(resolved, root) for root in plugin_roots):
            sys.modules.pop(name, None)


def _is_relative_to(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


if __name__ == "__main__":
    raise SystemExit(main())
