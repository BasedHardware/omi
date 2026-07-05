#!/usr/bin/env python3
"""Phase 1.2 gate: assert no route handler has a ``data: dict`` body parameter.

Every JSON request body must be a Pydantic model so FastAPI validates the shape
and the OpenAPI spec carries a real schema. The only exception is the allowlist
below — external webhooks whose payload shape is defined by a third party and
parsed defensively downstream.

Exit 0 if clean; exit 1 if any unjustified ``data: dict`` remains.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROUTER_DIR = pathlib.Path(__file__).resolve().parent.parent / "routers"
METHODS = {"get", "post", "put", "patch", "delete", "api_route", "head", "options", "websocket"}

# (file, function_name) -> reason
LEGIT_FREE_FORM: dict[tuple[str, str], str] = {
    ("agents.py", "hume_expression_measurement_callback"): (
        "External Hume AI webhook; payload is an arbitrarily-nested prosody "
        "structure forwarded wholesale to HumeJobCallbackModel.from_dict."
    ),
}


def _is_route_handler(node: ast.AST) -> bool:
    for dec in getattr(node, "decorator_list", []):
        call = dec if isinstance(dec, ast.Call) else None
        if call and isinstance(call.func, ast.Attribute) and call.func.attr in METHODS:
            return True
    return False


def _has_data_dict_arg(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    # Inspect every parameter kind (positional, positional-only, keyword-only)
    # so a `def route(*, data: dict)` cannot bypass the gate.
    all_args = list(node.args.args) + list(node.args.kwonlyargs) + list(node.args.posonlyargs)
    for arg in all_args:
        ann = arg.annotation
        if arg.arg == "data" and isinstance(ann, ast.Name) and ann.id == "dict":
            return True
        # also catch data: Dict / dict[str, ...]
        if (
            arg.arg == "data"
            and isinstance(ann, ast.Subscript)
            and isinstance(ann.value, ast.Name)
            and ann.value.id in ("dict", "Dict")
        ):
            return True
    return False


def main() -> int:
    offenders = []
    for p in sorted(ROUTER_DIR.glob("*.py")):
        if p.name == "__init__.py":
            continue
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _is_route_handler(node)
                and _has_data_dict_arg(node)
            ):
                key = (p.name, node.name)
                if key not in LEGIT_FREE_FORM:
                    offenders.append((p.name, node.lineno, node.name))

    if offenders:
        print("❌ data: dict body params remain (convert to Pydantic request model):")
        for f, line, fn in offenders:
            print(f"  {f}:{line} {fn}")
        return 1
    print(f"✅ Zero unjustified data:dict body params ({len(LEGIT_FREE_FORM)} allowlisted free-form).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
