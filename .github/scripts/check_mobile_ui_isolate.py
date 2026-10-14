#!/usr/bin/env python3
"""INV-PERF-1: keep the Flutter UI isolate free for frames.

The mobile app was intermittently laggy while syncing or recording: scrolling, page
transitions and taps stalled because work that grows with the user's history ran on the UI
isolate (whole-index WAL JSON rewrites, full-transcript fingerprints, synchronous directory
listings) and because state hooks re-notified on every upstream change. See
app/docs/performance.md.

Two guards:

1. A per-file no-increase ratchet (like INV-UI-3) over the patterns below. For every changed
   Dart file under app/lib/, no rule's count may rise above the file's count at the merge base;
   a new file starts at zero. Existing debt may remain and is expected to shrink.

2. An absolute check on the root provider graph: every ChangeNotifierProxyProvider update hook
   named in app/lib/main.dart (`previous?..hook(...)`) runs on each upstream notify, so a hook
   that calls notifyListeners() must return early when nothing changed: an `identical(...)` or
   `==` test and a `return` before the first notify. A hook with no such guard, or whose
   declaration cannot be read, fails.

Escape hatch: on the offending line (for a proxy hook, its declaration line) or on the line
directly above it, write
    // omi-perf-allow: <rule-id> -- <reason>
(several ids may be comma-separated). The reason is required. The line above survives
`dart format`, which moves a trailing comment after `{` into the body.

Usage:
    check_mobile_ui_isolate.py --changed-files FILE --base REF   # ratchet + provider graph (CI)
    check_mobile_ui_isolate.py --report app/lib/pages/foo.dart   # counts for files, no base
    check_mobile_ui_isolate.py --graph                           # provider graph check only
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from check_mobile_ux_contract import STRING_LITERAL, _in_comment, _in_string, _line_bounds, git_show

APP_ROOT = "app/lib/"
MAIN_DART = "app/lib/main.dart"
EXCLUDED_PREFIXES = ("app/lib/gen/", "app/lib/l10n/")
EXCLUDED_SUFFIXES = (".g.dart", ".gen.dart", ".freezed.dart", ".mocks.dart")
ALLOW = re.compile(r"//\s*omi-perf-allow:\s*([\w\-, ]+?)\s+--\s+\S")

SYNC_IO_METHODS = (
    "readAsStringSync|readAsBytesSync|readAsLinesSync|writeAsStringSync|writeAsBytesSync|listSync|"
    "existsSync|lengthSync|statSync|openSync|writeFromSync|flushSync|createSync|deleteSync|renameSync|"
    "copySync|lastModifiedSync"
)
IMAGE_SIZE_HINT = re.compile(r"\b(cacheWidth|cacheHeight|memCacheWidth|memCacheHeight|maxWidthDiskCache|ResizeImage)\b")
# A periodic timer faster than this many milliseconds is a frame-rate driver.
FAST_TIMER_MS = 100


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    fix: str
    # Extra test on the match (text, match) -> counts?
    accept: object = None
    # Only files whose repo path matches count for this rule.
    path_filter: re.Pattern[str] | None = None


def _call_args(text: str, open_paren: int) -> str:
    """The text between the parenthesis at [open_paren] and its partner (best effort)."""
    depth = 0
    for index in range(open_paren, min(len(text), open_paren + 4000)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : index]
    return text[open_paren + 1 : open_paren + 4000]


def _unsized_image(text: str, match: re.Match[str]) -> bool:
    if re.search(r"\bResizeImage\s*\(\s*$", text[max(0, match.start() - 80) : match.start()]):
        return False  # ResizeImage(NetworkImage(url), width: …) decodes at display size
    return not IMAGE_SIZE_HINT.search(_call_args(text, match.end() - 1))


def _fast_timer(_text: str, match: re.Match[str]) -> bool:
    if match.group("unit") == "microseconds":
        return int(match.group("ms")) < FAST_TIMER_MS * 1000
    return int(match.group("ms")) < FAST_TIMER_MS


PROVIDER_PATH = re.compile(r"^app/lib/(providers/.*|.*_provider)\.dart$")
# Modules whose JSON grows with the user's history; they must encode/decode through offUiIsolate.
HISTORY_JSON_PATH = re.compile(
    r"^app/lib/(utils/wal_file_manager|services/capture/local_segment_store|backend/http/api/conversations"
    r"|backend/preferences)\.dart$"
)


def _outside_off_ui_isolate(text: str, match: re.Match[str]) -> bool:
    """False when the match sits inside an `offUiIsolate(...)` call's arguments."""
    masked = _mask(text)
    for call in re.finditer(r"\boffUiIsolate\s*(?:<[^>(]*>)?\s*\(", masked[: match.start()]):
        open_paren = call.end() - 1
        if _matching(masked, open_paren, "(", ")") > match.start():
            return False
    return True

RULES: tuple[Rule, ...] = (
    Rule(
        "sync-file-io",
        re.compile(rf"\.(?:{SYNC_IO_METHODS})\s*\("),
        "the async File/Directory API (await file.readAsString(), dir.list(), FileStat.stat)",
    ),
    Rule(
        "json-in-provider",
        re.compile(r"\bjson(?:En|De)code\s*\("),
        "parse in the API/persistence layer; for collections use offUiIsolate (lib/utils/off_ui_isolate.dart)",
        path_filter=PROVIDER_PATH,
    ),
    Rule(
        "history-json-on-ui",
        re.compile(r"\bjson(?:En|De)code\s*\("),
        "offUiIsolate (lib/utils/off_ui_isolate.dart); this module's JSON grows with the user's history",
        accept=_outside_off_ui_isolate,
        path_filter=HISTORY_JSON_PATH,
    ),
    Rule(
        "fast-periodic-timer",
        re.compile(r"Timer\.periodic\(\s*(?:const\s+)?Duration\(\s*(?P<unit>milliseconds|microseconds):\s*(?P<ms>\d+)"),
        "an AnimationController/Ticker, or a dedicated ValueNotifier only the painting widget listens to",
        accept=_fast_timer,
    ),
    Rule(
        "blur-filter",
        re.compile(r"\bBackdropFilter\s*\(|\bImageFilter\.blur\s*\("),
        "a translucent fill; never blur inside a scrolling list or a surface that stays on screen",
    ),
    Rule(
        "unsized-network-image",
        re.compile(r"(?<![\w.])(?:CachedNetworkImage|CachedNetworkImageProvider|NetworkImage|Image\.network)\s*\("),
        "memCacheWidth/cacheWidth (decode at display size, not full resolution)",
        accept=_unsized_image,
    ),
    Rule(
        "shrink-wrap-list",
        re.compile(r"\bshrinkWrap\s*:\s*true\b"),
        "a sliver (CustomScrollView + SliverList); shrinkWrap lays out every child up front",
    ),
)
RULE_IDS: tuple[str, ...] = tuple(rule.id for rule in RULES)
PROXY_HOOK_RULE = "proxy-hook-notify"


def is_contract_source(path: str) -> bool:
    if not path.startswith(APP_ROOT) or not path.endswith(".dart"):
        return False
    if path.startswith(EXCLUDED_PREFIXES) or path.endswith(EXCLUDED_SUFFIXES):
        return False
    return True


def _allowed(line: str, rule_id: str) -> bool:
    match = ALLOW.search(line)
    if not match:
        return False
    return rule_id in {part.strip() for part in match.group(1).split(",")}


def _allowed_at(text: str, line_start: int, line_end: int, rule_id: str) -> bool:
    """The allow comment may sit on the line itself or alone on the line directly above."""
    if _allowed(text[line_start:line_end], rule_id):
        return True
    if line_start == 0:
        return False
    above_start, above_end = _line_bounds(text, line_start - 1)
    above = text[above_start:above_end]
    return above.lstrip().startswith("//") and _allowed(above, rule_id)


def _in_interpolation(line: str, column: int) -> bool:
    """True when [column] is inside a `${...}` interpolation, which is executable code."""
    for match in re.finditer(r"\$\{", line):
        depth = 0
        for index in range(match.end() - 1, len(line)):
            if line[index] == "{":
                depth += 1
            elif line[index] == "}":
                depth -= 1
                if depth == 0:
                    if match.end() <= column < index:
                        return True
                    break
    return False


def find_hits(text: str, path: str = "app/lib/x.dart") -> dict[str, list[int]]:
    """Map rule id -> 1-based line numbers of every counted hit in [text]."""
    hits: dict[str, list[int]] = {rule_id: [] for rule_id in RULE_IDS}
    for rule in RULES:
        if rule.path_filter is not None and not rule.path_filter.match(path):
            continue
        for match in rule.pattern.finditer(text):
            start, end = _line_bounds(text, match.start())
            line = text[start:end]
            column = match.start() - start
            if _in_comment(line, column) or (_in_string(line, column) and not _in_interpolation(line, column)):
                continue
            if rule.accept is not None and not rule.accept(text, match):  # type: ignore[operator]
                continue
            if _allowed_at(text, start, end, rule.id):
                continue
            hits[rule.id].append(text.count("\n", 0, match.start()) + 1)
    return hits


def count_hits(text: str, path: str = "app/lib/x.dart") -> dict[str, int]:
    return {rule_id: len(lines) for rule_id, lines in find_hits(text, path).items()}


def fix_for(rule_id: str) -> str:
    return next(rule.fix for rule in RULES if rule.id == rule_id)


def compare(path: str, head_text: str, base_text: str | None) -> list[str]:
    """Regression lines for one file (empty when no rule's count rose)."""
    head_hits = find_hits(head_text, path)
    base_counts = count_hits(base_text, path) if base_text is not None else {rule_id: 0 for rule_id in RULE_IDS}
    regressions: list[str] = []
    for rule_id in RULE_IDS:
        head_count = len(head_hits[rule_id])
        if head_count > base_counts[rule_id]:
            lines = ", ".join(str(n) for n in head_hits[rule_id][:8])
            more = "…" if head_count > 8 else ""
            regressions.append(
                f"{path}: {rule_id} {base_counts[rule_id]} → {head_count} (lines {lines}{more}); use {fix_for(rule_id)}"
            )
    return regressions


# ── provider graph ────────────────────────────────────────────────────────────

# `previous?..hook(...)` (cascade) and `previous?.hook(...); return previous;` (block form).
PROXY_HOOK_CALL = re.compile(r"\bprevious\s*[?!]?\.\.?\s*(\w+)\s*\(")
LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def proxy_hooks(main_text: str) -> list[str]:
    return sorted(set(PROXY_HOOK_CALL.findall(_mask(main_text))))


def _mask(text: str) -> str:
    """Blank out comments and string literals, keeping offsets."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    text = BLOCK_COMMENT.sub(blank, text)
    text = STRING_LITERAL.sub(blank, text)
    return LINE_COMMENT.sub(blank, text)


def _matching(text: str, open_index: int, open_char: str, close_char: str) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return len(text)


def _hook_body(masked: str, after_params: int) -> tuple[str, bool] | None:
    """(body, is_arrow) for the declaration whose parameter list ends at [after_params]."""
    rest = re.match(r"\s*(?:async\s*)?(\{|=>)", masked[after_params:])
    if not rest:
        return None
    start = after_params + rest.end(1) - 1
    if rest.group(1) == "{":
        return masked[start + 1 : _matching(masked, start, "{", "}")], False
    end = masked.find(";", start)
    return masked[start + 2 : end if end != -1 else len(masked)], True


CONTROL_KEYWORDS = ("if", "for", "while", "switch", "catch")
CONTROL_BLOCK_WORDS = ("else", "try", "finally", "do")


def _opens_control_block(body: str, brace: int) -> bool:
    """True when the `{` at [brace] opens an if/else/loop/try block, not a closure or literal."""
    before = body[:brace].rstrip()
    if before.endswith(CONTROL_BLOCK_WORDS) and re.search(r"\b(?:else|try|finally|do)$", before):
        return True
    if not before.endswith(")"):
        return False
    depth = 0
    for index in range(len(before) - 1, -1, -1):
        char = before[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth == 0:
                return re.search(rf"\b(?:{'|'.join(CONTROL_KEYWORDS)})\s*$", before[:index]) is not None
    return False


def _in_hook_scope(body: str, position: int) -> bool:
    """True when [position] is in the hook's own body or its if/else/loop/try blocks, not a closure."""
    stack: list[bool] = []
    for match in re.finditer(r"[{}]", body[:position]):
        if match.group(0) == "{":
            stack.append(_opens_control_block(body, match.start()))
        elif stack:
            stack.pop()
    return all(stack)


UNCHANGED_TEST = re.compile(r"\bidentical\s*\(|==(?!\s*null\b)")


def _parameter_names(params: str) -> set[str]:
    """Names declared in a parameter list (`Foo p, {required Bar b}` -> {p, b})."""
    names = set()
    for part in re.split(r",", re.sub(r"[{}\[\]]", ",", params)):
        part = part.split("=")[0].strip()
        found = re.findall(r"([A-Za-z_]\w*)\s*$", part)
        if found and found[0] not in {"required", "this"}:
            names.add(found[0])
    return names


def _guarded_before(body: str, limit: int, params: set[str]) -> bool:
    """True when, before [limit], an `if` whose condition is an identical/== test on the injected
    values returns.

    The return must be that `if`'s own branch (`if (same) return;` or `if (same) { return; }`),
    and the condition must name a parameter or a local computed from one, so an unrelated
    equality (`if (disposed == true) return;`) does not count.
    """
    prefix = body[:limit]
    injected = set(params)
    locals_ = set(re.findall(r"\b(?:final|var)\s+([A-Za-z_]\w*)\s*=", body))
    stored = {
        name
        for name in re.findall(r"(?<![\w.])(?:this\.)?([A-Za-z_]\w*)\s*=(?!=)", body)
        if name not in locals_ and name not in params
    }
    for local in re.finditer(r"\b(?:final|var|[A-Z]\w*(?:<[^;=]*>)?\??)\s+([A-Za-z_]\w*)\s*=\s*([^;]*);", prefix):
        if any(re.search(rf"\b{re.escape(name)}\b", local.group(2)) for name in injected):
            injected.add(local.group(1))
    for match in re.finditer(r"\bif\s*\(", prefix):
        if not _in_hook_scope(body, match.start()):
            continue
        open_paren = match.end() - 1
        close = _matching(prefix, open_paren, "(", ")")
        condition = prefix[open_paren + 1 : close] if close < len(prefix) else ""
        if not UNCHANGED_TEST.search(condition):
            continue
        if not any(re.search(rf"\b{re.escape(name)}\b", condition) for name in injected):
            continue
        # ...and compare it with the backing reference the hook stores (a field it assigns).
        if not any(re.search(rf"\b{re.escape(name)}\b", condition) for name in stored):
            continue
        if re.match(r"\s*(?:\{\s*)?return\b", prefix[close + 1 :]):
            return True
    return False


def hook_violations(name: str, sources: dict[str, str]) -> list[str]:
    """Declarations of [name] that notify with no early return before the first notify.

    A hook named in main.dart with no recognisable declaration is itself a violation, so a
    declaration shape this parser does not understand cannot pass vacuously.
    """
    declaration = re.compile(
        rf"^[ \t]*(?:(?:void|Future<void>|FutureOr<void>)\s+)?{re.escape(name)}\s*\(", re.MULTILINE
    )
    problems: list[str] = []
    found = False
    for path, text in sources.items():
        masked = _mask(text)
        for match in declaration.finditer(masked):
            close = _matching(masked, masked.index("(", match.start()), "(", ")")
            parsed = _hook_body(masked, close + 1)
            if parsed is None:
                continue  # a call statement, not a declaration
            found = True
            start, end = _line_bounds(text, match.start())
            if _allowed_at(text, start, end, PROXY_HOOK_RULE):
                continue
            body, is_arrow = parsed
            notify = body.find("notifyListeners()")
            if notify == -1:
                continue
            params = _parameter_names(masked[masked.index("(", match.start()) + 1 : close])
            if not is_arrow and _guarded_before(body, notify, params):
                continue
            line = text.count("\n", 0, match.start()) + 1
            problems.append(
                f"{path}:{line}: {name}() is a proxy update hook (app/lib/main.dart) and notifies without an "
                f"early return; return when the injected references are unchanged"
            )
    if not found:
        problems.append(
            f"{MAIN_DART}: proxy update hook {name}() has no declaration this check can read; "
            f"declare it as `void {name}(...) {{ ... }}`"
        )
    return problems


def check_provider_graph(root: Path) -> list[str]:
    main_file = root / MAIN_DART
    if not main_file.is_file():
        return []
    hooks = proxy_hooks(main_file.read_text(encoding="utf-8", errors="ignore"))
    if not hooks:
        # The root graph has proxy providers today; finding none means the parser no longer
        # recognises their shape, and an empty check would pass vacuously.
        return [f"{MAIN_DART}: no `previous?..hook(...)` / `previous?.hook(...)` proxy update hooks found; update PROXY_HOOK_CALL"]
    sources: dict[str, str] = {}
    for file in sorted((root / APP_ROOT).rglob("*.dart")):
        rel = file.relative_to(root).as_posix()
        if is_contract_source(rel):
            sources[rel] = file.read_text(encoding="utf-8", errors="ignore")
    problems: list[str] = []
    for hook in hooks:
        problems.extend(hook_violations(hook, sources))
    return problems


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--changed-files", help="File listing changed paths (one per line).")
    parser.add_argument("--base", default=None, help="Git ref for the merge-base content.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--report", nargs="*", metavar="PATH", help="Print per-rule counts for these files and exit.")
    parser.add_argument("--graph", action="store_true", help="Run only the provider graph check.")
    return parser.parse_args(argv)


def _print_graph_failure(problems: list[str]) -> None:
    print("FAIL: INV-PERF-1 — a proxy update hook re-notifies on every upstream change.")
    print("Return early when nothing changed, or put")
    print("`// omi-perf-allow: proxy-hook-notify -- <reason>` on the line above the declaration.")
    print("See app/docs/performance.md")
    for line in problems:
        print(f"  - {line}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()

    if args.report is not None:
        for path in args.report:
            text = (root / path).read_text(encoding="utf-8", errors="ignore")
            counts = {k: v for k, v in count_hits(text, path).items() if v}
            print(f"{path}: {counts or 'clean'}")
        return 0

    graph_problems = check_provider_graph(root)
    if args.graph:
        if graph_problems:
            _print_graph_failure(graph_problems)
            return 1
        print("OK: INV-PERF-1 — every proxy update hook returns early before notifying.")
        return 0

    if not args.changed_files:
        print("FAIL: --changed-files is required (or use --report / --graph).")
        return 1
    changed = [
        line.strip()
        for line in Path(args.changed_files).read_text(encoding="utf-8").splitlines()
        if line.strip() and is_contract_source(line.strip())
    ]
    if not changed:
        print("OK: no app/lib Dart sources in changed files for INV-PERF-1.")
        return 0
    if not args.base:
        print("FAIL: --base is required for the UI isolate ratchet.")
        return 1

    regressions: list[str] = []
    for path in changed:
        head_file = root / path
        if not head_file.is_file():
            continue
        head_text = head_file.read_text(encoding="utf-8", errors="ignore")
        regressions.extend(compare(path, head_text, git_show(args.base, path, root)))

    failed = False
    if regressions:
        failed = True
        print("FAIL: INV-PERF-1 — UI-isolate cost patterns increased in changed files.")
        print("Use the suggested alternative (app/docs/performance.md), or put")
        print("`// omi-perf-allow: <rule> -- <reason>` on the line or the line above.")
        print("See product/invariants/mobile-ui-isolate.md")
        for line in regressions:
            print(f"  - {line}")
    if graph_problems:
        failed = True
        _print_graph_failure(graph_problems)
    if failed:
        return 1

    print(f"OK: INV-PERF-1 — no UI-isolate cost increase across {len(changed)} changed app/lib file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
