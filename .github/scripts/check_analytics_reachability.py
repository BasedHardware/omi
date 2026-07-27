#!/usr/bin/env python3
"""Static tripwire for analytics methods orphaned from production callers.

This would have caught the Device Connected regression in 02524b7c0b: its
qualified Flutter call sites fell from two to one. It also rejects the dead
macOS shape removed with this checker: a production-called empty
reportAllSettingsIfNeeded() plus its unreachable collectAllSettings() helper.

This is deliberately lexical, not behavioral coverage. It recognizes the
repository's three analytics access boundaries, ignores comments and strings,
and ratchets current call-site counts. It does not prove that a call executes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / ".github/scripts/analytics_reachability_baseline.json"


@dataclass(frozen=True)
class Token:
    value: str
    kind: str = "punct"


@dataclass(frozen=True)
class Method:
    name: str
    public: bool
    body: tuple[Token, ...]


def lex(source: str) -> list[Token]:
    """Tokenize enough syntax to distinguish code from comments and strings."""
    tokens: list[Token] = []
    i = 0
    while i < len(source):
        char = source[i]
        if char.isspace():
            i += 1
            continue
        if source.startswith("//", i):
            i = source.find("\n", i)
            if i < 0:
                break
            continue
        if source.startswith("/*", i):
            depth = 1
            i += 2
            while i < len(source) and depth:
                if source.startswith("/*", i):
                    depth += 1
                    i += 2
                elif source.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue
        if char in "'\"`":
            quote = char
            triple = source.startswith(char * 3, i)
            delimiter = char * (3 if triple else 1)
            i += len(delimiter)
            value: list[str] = []
            while i < len(source):
                if source.startswith(delimiter, i):
                    i += len(delimiter)
                    break
                if source[i] == "\\" and not triple and i + 1 < len(source):
                    value.append(source[i + 1])
                    i += 2
                else:
                    value.append(source[i])
                    i += 1
            tokens.append(Token("".join(value), "string"))
            continue
        if char.isalpha() or char in "_$":
            end = i + 1
            while end < len(source) and (source[end].isalnum() or source[end] in "_$"):
                end += 1
            tokens.append(Token(source[i:end], "ident"))
            i = end
            continue
        if source.startswith("=>", i):
            tokens.append(Token("=>"))
            i += 2
            continue
        tokens.append(Token(char))
        i += 1
    return tokens


def matching(tokens: list[Token], start: int, opening: str, closing: str) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index].value == opening:
            depth += 1
        elif tokens[index].value == closing:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"unclosed {opening}")


def statement_end(tokens: list[Token], start: int) -> int:
    """Find a semicolon outside nested closures/collections."""
    depths = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    for index in range(start, len(tokens)):
        value = tokens[index].value
        if value in depths:
            depths[value] += 1
        elif value in pairs:
            depths[pairs[value]] -= 1
        elif value == ";" and not any(depths.values()):
            return index
    raise ValueError("unterminated statement")


def class_body(tokens: list[Token], name: str) -> tuple[int, int]:
    for index in range(len(tokens) - 2):
        if tokens[index].value == "class" and tokens[index + 1].value == name:
            brace = next(i for i in range(index + 2, len(tokens)) if tokens[i].value == "{")
            return brace, matching(tokens, brace, "{", "}")
    raise ValueError(f"class {name} not found")


def dart_methods(source: str) -> list[Method]:
    tokens = lex(source)
    start, end = class_body(tokens, "AnalyticsManager")
    methods: list[Method] = []
    depth = 1
    index = start + 1
    while index < end:
        value = tokens[index].value
        if value == "{":
            depth += 1
        elif value == "}":
            depth -= 1
        elif (
            depth == 1
            and tokens[index].kind == "ident"
            and index + 1 < end
            and tokens[index + 1].value == "("
            and value != "AnalyticsManager"
        ):
            close = matching(tokens, index + 1, "(", ")")
            after = close + 1
            while after < end and tokens[after].value in {"async", "sync", "*"}:
                after += 1
            if after < end and tokens[after].value in {"{", "=>"}:
                if tokens[after].value == "{":
                    body_end = matching(tokens, after, "{", "}")
                    body = tuple(tokens[after + 1 : body_end])
                else:
                    body_end = statement_end(tokens, after + 1)
                    body = tuple(tokens[after + 1 : body_end])
                methods.append(Method(value, not value.startswith("_"), body))
                index = body_end
        index += 1
    return methods


def swift_methods(source: str) -> list[Method]:
    tokens = lex(source)
    start, end = class_body(tokens, "AnalyticsManager")
    methods: list[Method] = []
    depth = 1
    index = start + 1
    while index < end:
        value = tokens[index].value
        if value == "{":
            depth += 1
        elif value == "}":
            depth -= 1
        elif depth == 1 and value == "func" and index + 1 < end:
            name = tokens[index + 1].value
            modifier_start = index - 1
            # `var`/`let` terminate the scan too: a stored property declared just above a func
            # (`private var x: T?` then `func setX(...)`) would otherwise donate its `private`.
            while modifier_start > start and tokens[modifier_start].value not in {"}", "{", ";", "var", "let"}:
                modifier_start -= 1
            modifiers = {token.value for token in tokens[modifier_start + 1 : index]}
            brace = next(i for i in range(index + 2, end) if tokens[i].value == "{")
            body_end = matching(tokens, brace, "{", "}")
            methods.append(
                Method(
                    name, not modifiers.intersection({"private", "fileprivate"}), tuple(tokens[brace + 1 : body_end])
                )
            )
            index = body_end
        index += 1
    return methods


def typescript_methods(source: str) -> list[Method]:
    tokens = lex(source)
    methods: list[Method] = []
    for index in range(len(tokens) - 2):
        if tokens[index].value != "export" or tokens[index + 1].value != "function":
            continue
        name = tokens[index + 2].value
        opening = next(i for i in range(index + 3, len(tokens)) if tokens[i].value == "(")
        closing = matching(tokens, opening, "(", ")")
        brace = next(i for i in range(closing + 1, len(tokens)) if tokens[i].value == "{")
        body_end = matching(tokens, brace, "{", "}")
        methods.append(Method(name, True, tuple(tokens[brace + 1 : body_end])))
    return methods


def sequence_call_counts(tokens: list[Token], prefixes: tuple[tuple[str, ...], ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    values = [token.value for token in tokens]
    for index in range(len(values)):
        for prefix in prefixes:
            end = index + len(prefix)
            if tuple(values[index:end]) != prefix or end + 2 >= len(values):
                continue
            if values[end] == "." and tokens[end + 1].kind == "ident" and values[end + 2] == "(":
                name = values[end + 1]
                counts[name] = counts.get(name, 0) + 1
    return counts


def dart_call_counts(sources: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    prefixes = (
        ("AnalyticsManager", "(", ")"),
        ("AnalyticsManager",),
        ("PlatformManager", ".", "instance", ".", "analytics"),
    )
    for source in sources:
        for name, count in sequence_call_counts(lex(source), prefixes).items():
            counts[name] = counts.get(name, 0) + count
    return counts


def swift_call_counts(sources: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        for name, count in sequence_call_counts(lex(source), (("AnalyticsManager", ".", "shared"),)).items():
            counts[name] = counts.get(name, 0) + count
    return counts


def windows_imports(tokens: list[Token]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        if tokens[index].value != "import":
            index += 1
            continue
        try:
            opening = next(i for i in range(index + 1, len(tokens)) if tokens[i].value in {"{", ";"})
        except StopIteration:
            break
        if tokens[opening].value != "{":
            index = opening + 1
            continue
        closing = matching(tokens, opening, "{", "}")
        if closing + 2 >= len(tokens) or tokens[closing + 1].value != "from":
            index = closing + 1
            continue
        path = tokens[closing + 2]
        if path.kind != "string" or path.value.rsplit("/", 1)[-1] not in {"analytics", "analytics.ts"}:
            index = closing + 1
            continue
        cursor = opening + 1
        while cursor < closing:
            if tokens[cursor].kind != "ident":
                cursor += 1
                continue
            imported = tokens[cursor].value
            local = imported
            if cursor + 2 < closing and tokens[cursor + 1].value == "as":
                local = tokens[cursor + 2].value
                cursor += 3
            else:
                cursor += 1
            aliases[local] = imported
        index = closing + 3
    return aliases


def windows_call_counts(sources: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        tokens = lex(source)
        aliases = windows_imports(tokens)
        for index in range(len(tokens) - 1):
            imported = aliases.get(tokens[index].value)
            if imported and tokens[index + 1].value == "(":
                counts[imported] = counts.get(imported, 0) + 1
    return counts


def private_incoming(methods: list[Method]) -> dict[str, int]:
    private_names = {method.name for method in methods if not method.public}
    incoming = dict.fromkeys(private_names, 0)
    for caller in methods:
        for index in range(len(caller.body) - 1):
            callee = caller.body[index].value
            if callee in private_names and caller.name != callee and caller.body[index + 1].value == "(":
                incoming[callee] += 1
    return incoming


def audit_platform(
    platform: str,
    methods: list[Method],
    calls: dict[str, int],
    baseline: dict[str, dict[str, object]],
) -> list[str]:
    errors: list[str] = []
    by_name = {method.name: method for method in methods}
    if len(by_name) != len(methods):
        errors.append(f"{platform}: overloaded analytics methods are unsupported by this name-based tripwire")
        return errors

    orphans = set(baseline["public_orphans"].get(platform, []))
    private_orphans = set(baseline["private_orphans"].get(platform, []))
    minimums = baseline["multi_call_minimums"].get(platform, {})
    for stale in sorted((orphans | private_orphans | set(minimums)) - set(by_name)):
        errors.append(f"{platform}.{stale}: stale baseline entry; remove it")

    incoming = private_incoming(methods)
    for method in methods:
        if not method.body:
            errors.append(f"{platform}.{method.name}: empty analytics method")
        if method.public:
            count = calls.get(method.name, 0)
            if count == 0:
                if method.name not in orphans:
                    errors.append(f"{platform}.{method.name}: no production call site")
                continue
            if method.name in orphans:
                errors.append(f"{platform}.{method.name}: now has a caller; remove it from public_orphans")
            minimum = int(minimums.get(method.name, 1))
            if count < minimum:
                errors.append(f"{platform}.{method.name}: production call sites fell {minimum}->{count}")
            elif count > minimum and count > 1:
                errors.append(
                    f"{platform}.{method.name}: production call sites grew {minimum}->{count}; "
                    "raise multi_call_minimums to ratchet the gain"
                )
        else:
            count = incoming.get(method.name, 0)
            if count == 0 and method.name not in private_orphans:
                errors.append(f"{platform}.{method.name}: unreachable private analytics helper")
            elif count > 0 and method.name in private_orphans:
                errors.append(f"{platform}.{method.name}: now reachable; remove it from private_orphans")
    return errors


def load_platforms(root: Path) -> dict[str, tuple[list[Method], dict[str, int]]]:
    dart_manager = root / "app/lib/utils/analytics/analytics_manager.dart"
    swift_manager = root / "desktop/macos/Desktop/Sources/AnalyticsManager.swift"
    windows_manager = root / "desktop/windows/src/renderer/src/lib/analytics.ts"
    dart_sources = [
        path.read_text(encoding="utf-8") for path in (root / "app/lib").rglob("*.dart") if path != dart_manager
    ]
    swift_sources = [
        path.read_text(encoding="utf-8")
        for path in (root / "desktop/macos/Desktop/Sources").rglob("*.swift")
        if path != swift_manager
    ]
    windows_sources = [
        path.read_text(encoding="utf-8")
        for path in (root / "desktop/windows/src/renderer/src").rglob("*")
        if path.suffix in {".ts", ".tsx"}
        and ".test." not in path.name
        and ".spec." not in path.name
        and path != windows_manager
    ]
    return {
        "flutter": (dart_methods(dart_manager.read_text(encoding="utf-8")), dart_call_counts(dart_sources)),
        "macos": (swift_methods(swift_manager.read_text(encoding="utf-8")), swift_call_counts(swift_sources)),
        "windows": (
            typescript_methods(windows_manager.read_text(encoding="utf-8")),
            windows_call_counts(windows_sources),
        ),
    }


def suggested_baseline(platforms: dict[str, tuple[list[Method], dict[str, int]]]) -> dict[str, dict[str, object]]:
    baseline: dict[str, dict[str, object]] = {
        "public_orphans": {},
        "private_orphans": {},
        "multi_call_minimums": {},
    }
    for platform, (methods, calls) in platforms.items():
        incoming = private_incoming(methods)
        baseline["public_orphans"][platform] = sorted(
            method.name for method in methods if method.public and calls.get(method.name, 0) == 0
        )
        baseline["private_orphans"][platform] = sorted(
            method.name for method in methods if not method.public and incoming.get(method.name, 0) == 0
        )
        baseline["multi_call_minimums"][platform] = {
            method.name: calls[method.name]
            for method in sorted(methods, key=lambda item: item.name)
            if method.public and calls.get(method.name, 0) > 1
        }
    return baseline


def main() -> int:
    platforms = load_platforms(ROOT)
    if "--print-baseline" in sys.argv:
        print(json.dumps(suggested_baseline(platforms), indent=2, sort_keys=True))
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    errors = [
        error
        for platform, (methods, calls) in platforms.items()
        for error in audit_platform(platform, methods, calls, baseline)
    ]
    if errors:
        print("analytics reachability static tripwire failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("analytics reachability static tripwire passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
