#!/usr/bin/env python3
"""Generate the CLI command tree and inventory in docs/doc/developer/cli/commands.mdx.

Parses the Typer registrations in omi_cli/ with `ast` (no imports, no network,
no installed dependencies) so the docs page cannot drift from the code.

Usage:
  python3 tools/gen_commands_doc.py            # rewrite the generated sections
  python3 tools/gen_commands_doc.py --check    # exit 1 with a diff on drift
"""

from __future__ import annotations

import ast
import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]          # sdks/python-cli/
REPO = pathlib.Path(__file__).resolve().parents[3]         # repository root
DOC = REPO / "docs" / "doc" / "developer" / "cli" / "commands.mdx"

MAIN = ROOT / "omi_cli" / "main.py"
COMMANDS_DIR = ROOT / "omi_cli" / "commands"

BEGIN = "{/* BEGIN GENERATED:cli-commands */}"
END = "{/* END GENERATED:cli-commands */}"


def _const(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kwargs(call: ast.Call) -> dict[str, str]:
    out: dict[str, str] = {}
    for kw in call.keywords:
        if kw.arg and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            out[kw.arg] = kw.value.value
    return kw_only(call, out)


def kw_only(call: ast.Call, collected: dict[str, str]) -> dict[str, str]:
    return collected


def _decorator_command(dec: ast.AST, app_attr: str = "app") -> tuple[str, str] | None:
    """Return (name, help) from an @<app_attr>.command(...) decorator."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    if dec.func.attr != "command":
        return None
    if not isinstance(dec.func.value, ast.Name) or dec.func.value.id != app_attr:
        return None
    name = None
    help_text = ""
    if dec.args:
        first = _const(dec.args[0])
        if first:
            name = first
    for kw in dec.keywords:
        value = _const(kw.value)
        if value is None:
            continue
        if kw.arg == "name":
            name = value
        elif kw.arg == "help":
            help_text = " ".join(value.split())
    return (name, help_text)


def parse_module(path: pathlib.Path) -> tuple[list[ast.FunctionDef | ast.AsyncFunctionDef], list[ast.Call]]:
    """Return (functions, module-level calls) for a module parsed with ast."""
    tree = ast.parse(path.read_text())
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    calls = [n.value for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    return funcs, calls


def command_functions(path: pathlib.Path, app_attr: str = "app") -> list[tuple[str, str]]:
    """(command_name, help) for every @<app_attr>.command in source order; name defaults to function name."""
    funcs, _ = parse_module(path)
    out = []
    for fn in funcs:
        for dec in fn.decorator_list:
            hit = _decorator_command(dec)
            if hit is None:
                continue
            name, help_text = hit
            out.append((name or fn.name.replace("_", "-"), help_text))
            break
    return out


def nested_typer_groups(path: pathlib.Path) -> list[tuple[str, str, pathlib.Path]]:
    """(name, help, module) for every app.add_typer(mod.app, name=..., help=...) in main.py."""
    _, calls = parse_module(path)
    out = []
    for call in calls:
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "add_typer"):
            continue
        name = None
        help_text = ""
        for kw in call.keywords:
            value = _const(kw.value)
            if value is None:
                continue
            if kw.arg == "name":
                name = value
            elif kw.arg == "help":
                help_text = " ".join(value.split())
        if name is None:
            continue
        module = None
        if call.args and isinstance(call.args[0], ast.Attribute) and isinstance(call.args[0].value, ast.Name):
            module = call.args[0].value.id
        out.append((name, help_text, module))
    return out


def _module_path(module: str | None) -> pathlib.Path | None:
    if not module:
        return None
    for candidate in (COMMANDS_DIR / f"{module}.py", COMMANDS_DIR / f"{module.removesuffix('_cmd')}.py"):
        if candidate.exists():
            return candidate
    return None


def collect() -> dict:
    main_cmds = command_functions(MAIN)
    groups = []
    for name, help_text, module in nested_typer_groups(MAIN):
        path = _module_path(module)
        entry: dict = {"name": name, "help": help_text, "commands": [], "subgroups": []}
        if path is not None:
            entry["commands"] = command_functions(path)
            # nested groups declared inside the module: x_app = typer.Typer(); app.add_typer(x_app, name=...)
            funcs, calls = parse_module(path)
            tree = ast.parse(path.read_text())
            typer_vars = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                    continue
                func = node.value.func
                is_typer = (
                    (isinstance(func, ast.Name) and func.id == "Typer")
                    or (isinstance(func, ast.Attribute) and func.attr == "Typer")
                )
                if is_typer:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            typer_vars.add(target.id)
            for call in calls:
                if not (isinstance(call.func, ast.Attribute) and call.func.attr == "add_typer"):
                    continue
                sub_name, sub_help = None, ""
                for kw in call.keywords:
                    value = _const(kw.value)
                    if value is None:
                        continue
                    if kw.arg == "name":
                        sub_name = value
                    elif kw.arg == "help":
                        sub_help = " ".join(value.split())
                if sub_name is None:
                    continue
                sub_cmds = []
                for fn in funcs:
                    for dec in fn.decorator_list:
                        if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                                and dec.func.attr == "command"
                                and isinstance(dec.func.value, ast.Name)
                                and dec.func.value.id in typer_vars
                                and dec.func.value.id != "app"):
                            hit = _decorator_command(dec, app_attr=dec.func.value.id)
                            if hit:
                                sub_name_x, sub_help_x = hit
                                sub_cmds.append((sub_name_x or fn.name.replace("_", "-"), sub_help_x))
                            break
                entry["subgroups"].append({"name": sub_name, "help": sub_help, "commands": sub_cmds})
        groups.append(entry)
    return {"commands": main_cmds, "groups": groups}


def render_tree(data: dict) -> str:
    lines = ["omi"]
    entries = [(name, None) for name, _ in data["commands"]] + [(g["name"], g) for g in data["groups"]]
    for i, (name, group) in enumerate(entries):
        last = i == len(entries) - 1
        branch = "`--" if last else "|--"
        if group is None:
            lines.append(f"{branch} {name}")
        else:
            child_bits = [c for c, _ in group["commands"]]
            for sub in group["subgroups"]:
                child_bits.append(f"{sub['name']} {{{', '.join(n for n, _ in sub['commands'])}}}")
            body = f"{' | '.join(child_bits)}" if child_bits else group["help"]
            lines.append(f"{branch} {group['name']:<14} {body}")
    return "\n".join(lines)


def render_inventory(data: dict) -> str:
    parts = []
    if data["commands"]:
        rows = ["| Command | Help |", "| --- | --- |"]
        for name, help_text in data["commands"]:
            rows.append(f"| `omi {name}` | {help_text} |")
        parts.append("\n".join(rows))
    for group in data["groups"]:
        title = f"**`omi {group['name']}`** — {group['help']}"
        rows = ["| Command | Help |", "| --- | --- |"]
        for name, help_text in group["commands"]:
            rows.append(f"| `omi {group['name']} {name}` | {help_text} |")
        for sub in group["subgroups"]:
            for name, help_text in sub["commands"]:
                rows.append(f"| `omi {group['name']} {sub['name']} {name}` | {help_text} |")
        parts.append(f"{title}\n\n" + "\n".join(rows))
    return "\n\n".join(parts)


def generated_block(data: dict) -> str:
    tree = render_tree(data)
    inventory = render_inventory(data)
    return (
        f"{BEGIN}\n"
        "{/* Generated by sdks/python-cli/tools/gen_commands_doc.py from the Typer\n"
        "registrations in omi_cli/. Edit the script, not this block. */}\n"
        f"```text\n{tree}\n```\n\n"
        "## Command inventory\n\n"
        f"{inventory}\n"
        f"{END}"
    )


def main() -> int:
    data = collect()
    block = generated_block(data)
    text = DOC.read_text()
    if BEGIN in text and END in text:
        head = text.split(BEGIN)[0]
        tail = text.split(END)[1]
        new = head + block + tail
    else:
        # First run: insert after the intro paragraph (before "## Global flags").
        marker = "## Global flags"
        head, tail = text.split(marker, 1)
        new = head + block + "\n\n---\n\n" + marker + tail
    if "--check" in sys.argv:
        if new == text:
            print("cli commands doc: up to date")
            return 0
        diff = difflib.unified_diff(text.splitlines(True), new.splitlines(True),
                                    fromfile=str(DOC), tofile=str(DOC) + " (expected)")
        sys.stdout.writelines(diff)
        return 1
    DOC.write_text(new)
    print(f"wrote {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
