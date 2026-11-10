#!/usr/bin/env python3
"""INV-PERF-1: keep the Flutter UI isolate free for frames.

The mobile app was intermittently laggy while syncing or recording: scrolling, page
transitions and taps stalled because work that grows with the user's history ran on the UI
isolate (whole-index WAL JSON rewrites, full-transcript fingerprints, synchronous directory
listings) and because state hooks re-notified on every upstream change. See
app/docs/performance.md.

Three guards:

1. A per-file no-increase ratchet (like INV-UI-3) over the patterns below. For every changed
   Dart file under app/lib/, no rule's count may rise above the file's count at the merge base;
   a new file starts at zero. Existing debt may remain and is expected to shrink.
   Scoped rules also cover global input wrappers, unselected high-frequency provider
   subscriptions, JSON/sorts in builds and same-file build helpers, and list-item layers.

2. An absolute check on the root provider graph: every ChangeNotifierProxyProvider update hook
   named in app/lib/main.dart (`previous?..hook(...)`) runs on each upstream notify, so a hook
   that calls notifyListeners() must return early when nothing changed: an `identical(...)` or
   `==` test and a `return` before the first notify. A hook with no such guard, or whose
   declaration cannot be read, fails.

3. Absolute semantics ownership: ensureSemantics() is forbidden outside the explicit,
   call-specific SEMANTICS_ALLOWLIST, including in existing/unchanged files (#23400).
   Merge-base debt and inline allow comments cannot suppress this rule.

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
from functools import lru_cache
from pathlib import Path

from check_mobile_ux_contract import _line_bounds, git_show

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
# Deliberately empty after #23400. Keys are (repo path, whitespace-free masked
# source line), values are reviewed owner/lifetime reasons. Each entry permits
# ONE call, never an entire file or all future calls in an existing owner.
SEMANTICS_ALLOWLIST: dict[tuple[str, str], str] = {}


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    fix: str
    # Extra test on the match (text, match) -> counts?
    accept: object = None
    # Only files whose repo path matches count for this rule.
    path_filter: re.Pattern[str] | None = None
    absolute: bool = False


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
    text = _mask(text)
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
        "forced-semantics",
        re.compile(r"\bensureSemantics\s*\("),
        "read existing render-object annotations on demand; do not hold a SemanticsHandle (#23400). "
        "A necessary accessibility owner needs an explicit, call-specific SEMANTICS_ALLOWLIST review",
        absolute=True,
    ),
    Rule(
        "global-input-listener",
        re.compile(r"(?<![\w.])(?:Listener|NotificationListener)\s*(?:<[^>()]*>)?\s*\("),
        "scope input observation to the affected surface, keep callbacks bounded, and measure the production wrapper",
    ),
    Rule(
        "unselected-provider-listener",
        re.compile(r"(?:\?\.|\.\.|\.)addListener\s*\("),
        "Selector/context.select or a dedicated leaf ValueListenable; imperative callbacks must return on an unchanged selected key",
        accept=lambda text, match: _unselected_provider_listener(text, match),
    ),
    Rule(
        "json-in-build",
        re.compile(r"\b(?:jsonDecode|json\s*\.\s*decode)\s*\("),
        "decode before build in the data layer; use offUiIsolate for history-sized payloads",
        accept=lambda text, match: _in_ui_scope(text, match.start(), "build") and _outside_off_ui_isolate(text, match),
    ),
    Rule(
        "sort-in-build",
        re.compile(r"(?:\?\.)?\.sort\s*\("),
        "memoize history-sized ordering on a data/version key before build; document a measured bounded sort locally",
        accept=lambda text, match: _in_ui_scope(text, match.start(), "build") and _outside_off_ui_isolate(text, match),
    ),
    Rule(
        "list-item-layer",
        re.compile(r"(?<![\w.])Opacity\s*\(|\.saveLayer\s*\("),
        "paint alpha directly for simple content, or a measured leaf transition; avoid an offscreen layer per list row",
        accept=lambda text, match: _in_ui_scope(text, match.start(), "list"),
    ),
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


def find_hits(text: str, path: str = "app/lib/x.dart") -> dict[str, list[int]]:
    """Map rule id -> 1-based line numbers of every counted hit in [text]."""
    hits: dict[str, list[int]] = {rule_id: [] for rule_id in RULE_IDS}
    masked = _mask(text)
    semantics_seen: set[tuple[str, str]] = set()
    for rule in RULES:
        if rule.path_filter is not None and not rule.path_filter.match(path):
            continue
        for match in rule.pattern.finditer(masked):
            start, end = _line_bounds(text, match.start())
            if rule.id == "global-input-listener":
                for position in _global_input_hits(text, match, path):
                    callback_start, callback_end = _line_bounds(text, position)
                    if not _allowed_at(text, callback_start, callback_end, rule.id):
                        hits[rule.id].append(text.count("\n", 0, position) + 1)
                continue
            if rule.id == "forced-semantics":
                key = (path, re.sub(r"\s+", "", masked[start:end]))
                if key in SEMANTICS_ALLOWLIST and key not in semantics_seen:
                    semantics_seen.add(key)
                    continue
            if rule.accept is not None and not rule.accept(text, match):  # type: ignore[operator]
                continue
            if not rule.absolute and _allowed_at(text, start, end, rule.id):
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
        rule = next(rule for rule in RULES if rule.id == rule_id)
        if rule.absolute:
            base_counts[rule_id] = 0
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


def proxy_hooks(main_text: str) -> list[str]:
    return sorted(set(PROXY_HOOK_CALL.findall(_mask(main_text))))


@lru_cache(maxsize=32)
def _mask(text: str) -> str:
    """Dart lexical mask: preserve offsets/newlines and executable ${...} code.

    A scanner avoids interpreting URLs as comments or comments as strings; Dart
    supports raw/triple strings and nested block comments.
    """
    out = list(text)

    def blank(start: int, end: int) -> None:
        for pos in range(start, end):
            if text[pos] != "\n":
                out[pos] = " "

    def code(index: int, interpolation: bool = False) -> int:
        depth = 0
        while index < len(text):
            if text.startswith("//", index):
                end = text.find("\n", index)
                end = len(text) if end < 0 else end
                blank(index, end)
                index = end
            elif text.startswith("/*", index):
                start, nesting = index, 1
                index += 2
                while index < len(text) and nesting:
                    if text.startswith("/*", index):
                        nesting += 1
                        index += 2
                    elif text.startswith("*/", index):
                        nesting -= 1
                        index += 2
                    else:
                        index += 1
                blank(start, index)
            elif text[index] in "'\"" or (text[index] in "rR" and text[index + 1 : index + 2] in ("'", '"')):
                raw = text[index] in "rR"
                if raw:
                    blank(index, index + 1)
                    index += 1
                quote = text[index] * (3 if text.startswith(text[index] * 3, index) else 1)
                blank(index, index + len(quote))
                index += len(quote)
                while index < len(text):
                    if text.startswith(quote, index):
                        blank(index, index + len(quote))
                        index += len(quote)
                        break
                    if not raw and text.startswith("${", index):
                        blank(index, index + 2)
                        index = code(index + 2, True)
                    elif not raw and text[index] == "\\":
                        end = min(len(text), index + 2)
                        blank(index, end)
                        index = end
                    else:
                        blank(index, index + 1)
                        index += 1
            elif interpolation and text[index] == "}" and depth == 0:
                blank(index, index + 1)
                return index + 1
            else:
                if text[index] == "{":
                    depth += 1
                elif text[index] == "}":
                    depth -= 1
                index += 1
        return index

    code(0)
    return "".join(out)


def _expression_end(masked: str, start: int) -> int:
    """End of an arrow body/argument, respecting nested calls and literals."""
    stack: list[str] = []
    for index in range(start, len(masked)):
        char = masked[index]
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack:
                return index
            stack.pop()
        elif char in ",;" and not stack:
            return index
    return len(masked)


def _body_span(masked: str, after_params: int) -> tuple[int, int] | None:
    match = re.match(r"\s*(?:async\s*)?(\{|=>)", masked[after_params:])
    if not match:
        return None
    start = after_params + match.end()
    if match.group(1) == "{":
        return start, _matching(masked, start - 1, "{", "}")
    return start, _expression_end(masked, start)


@lru_cache(maxsize=32)
def _declarations(masked: str) -> tuple[tuple[str, int, int], ...]:
    # Local scope resolution, not a Dart type checker. Require a declaration
    # prefix so `return helper(...)` and ordinary calls are never declarations.
    pattern = re.compile(
        r"^[ \t]*(?:(?:static|Future|Widget|void|bool|int|double|String|List|Map|Set|[A-Z]\w*)"
        r"[\w<>?, .\[\]]*\s+)(\w+)\s*\(", re.M
    )
    found = set()
    # Dart permits inferred return types, including `build(context) => ...`.
    untyped = re.compile(r"^[ \t]*(\w+)\s*\(", re.M)
    for match in (*pattern.finditer(masked), *untyped.finditer(masked)):
        if match.group(1) in CONTROL_KEYWORDS:
            continue
        close = _matching(masked, match.end() - 1, "(", ")")
        span = _body_span(masked, close + 1)
        if span:
            found.add((match.group(1), *span))
    return tuple(sorted(found))


@lru_cache(maxsize=32)
def _classes(masked: str) -> tuple[tuple[str, int, int], ...]:
    return tuple((m.group(1), m.end(), _matching(masked, m.end() - 1, "{", "}"))
                 for m in re.finditer(r"\b(?:class|mixin|extension(?:\s+type)?)\s+(\w+)\b[^{}]*\{", masked))


def _owner(masked: str, position: int) -> tuple[int, int] | None:
    enclosing = [(start, end) for _, start, end in _classes(masked) if start <= position < end]
    return min(enclosing, key=lambda span: span[1] - span[0], default=None)


def _resolve_declarations(masked: str, name: str, position: int) -> list[tuple[int, int]]:
    owner = _owner(masked, position)
    candidates = [(a, b) for declared, a, b in _declarations(masked) if declared == name]
    local = [span for span in candidates if _owner(masked, span[0]) == owner]
    # An unqualified call may use a top-level helper, never another class's method.
    return local or [span for span in candidates if _owner(masked, span[0]) is None]


def _positional_row_callbacks(masked: str) -> list[tuple[int, int]]:
    spans = []
    for match in re.finditer(r"\bSliverChildBuilderDelegate\s*\(\s*", masked):
        start = match.end()
        if masked[start:start + 1] == "(":
            close = _matching(masked, start, "(", ")")
            span = _body_span(masked, close + 1)
            if span:
                spans.append(span)
        else:
            ref = re.match(r"(?:this\.)?(\w+)\b", masked[start:])
            if ref:
                spans.extend(_resolve_declarations(masked, ref.group(1), start))
    return spans


def _callback_spans(masked: str, names: str) -> list[tuple[int, int]]:
    spans = []
    for match in re.finditer(rf"\b(?:{names})\s*:\s*", masked):
        start = match.end()
        if masked[start : start + 1] == "(":
            close = _matching(masked, start, "(", ")")
            span = _body_span(masked, close + 1)
            if span:
                spans.append(span)
        else:
            ref = re.match(r"(?:this\.)?(\w+)\b", masked[start:])
            if ref:
                spans.extend(_resolve_declarations(masked, ref.group(1), start))
    return spans


@lru_cache(maxsize=32)
def _deferred_spans(masked: str) -> tuple[tuple[int, int], ...]:
    # Mask only the callback argument at the registration site. Excluding a
    # named handler's declaration would hide it if build also calls it directly.
    return tuple(
        (match.end(), _expression_end(masked, match.end()))
        for match in re.finditer(r"\bon[A-Z]\w*\s*:\s*", masked)
    )


@lru_cache(maxsize=32)
def _ui_scopes(text: str, kind: str) -> tuple[tuple[int, int], ...]:
    masked = _mask(text)
    declarations = _declarations(masked)
    classes = _classes(masked)
    if kind == "build":
        spans = [(a, b) for name, a, b in declarations if name == "build"]
        spans += _callback_spans(masked, r"builder|itemBuilder|separatorBuilder")
    else:
        spans = _callback_spans(masked, r"itemBuilder|separatorBuilder")
        # Eager lists and slivers have children rather than itemBuilder.
        for match in re.finditer(r"\b(?:ListView|SliverList|SliverChildListDelegate)\s*\(", masked):
            spans.append((match.end(), _matching(masked, match.end() - 1, "(", ")")))
        # A reusable row can be built in another file: recognize its declared
        # role, rather than exempting/banning whole directories or filenames.
        for class_name, start, end in classes:
            if class_name.endswith(("ListItem", "Row", "Tile")):
                spans += [(a, b) for name, a, b in declarations if name == "build" and start <= a < end]
    spans += _positional_row_callbacks(masked)
    # Follow same-file helper calls and tear-offs, including row builders.
    # Cycles terminate; external helpers/types are outside this lexical guard.
    selected = set(spans)
    deferred = _deferred_spans(masked)

    def referenced(pattern: str) -> bool:
        return any(not any(a <= start + ref.start() < b for a, b in deferred)
                   for start, end in selected for ref in re.finditer(pattern, masked[start:end]))

    while True:
        added = set()
        declared_names = {name for name, _, _ in declarations}
        for start, end in selected:
            for ref in re.finditer(r"\b[A-Za-z_]\w*\b", masked[start:end]):
                position = start + ref.start()
                if ref.group() not in declared_names or any(a <= position < b for a, b in deferred):
                    continue
                prefix = masked[max(0, position - 6):position].rstrip()
                if prefix.endswith(".") and not prefix.endswith("this."):
                    continue
                added.update(_resolve_declarations(masked, ref.group(), position))
        if kind == "list":
            # List rows often construct a same-file widget/painter; only its
            # build/paint methods are row work, not initState or tap handlers.
            for class_name, start, end in classes:
                if referenced(rf"\b{re.escape(class_name)}\s*\("):
                    added.update((a, b) for name, a, b in declarations
                                 if name in {"build", "paint"} and start <= a < end)
        added -= selected
        if not added:
            return tuple(sorted(selected))
        selected.update(added)


def _in_ui_scope(text: str, position: int, kind: str) -> bool:
    if any(a <= position < b for a, b in _deferred_spans(_mask(text))):
        return False
    return any(start <= position < end for start, end in _ui_scopes(text, kind))


def _global_input_hits(text: str, match: re.Match[str], path: str) -> list[int]:
    masked = _mask(text)
    args = masked[match.end() : _matching(masked, match.end() - 1, "(", ")")]
    named = {}
    index = 0
    while index < len(args):
        end = _expression_end(args, index)
        argument = re.match(r"\s*(\w+)\s*:\s*", args[index:end])
        if argument:
            named[argument.group(1)] = (args[index + argument.end() : end], match.end() + index + argument.start(1))
        index = end + 1
    # Root entry points or arbitrary-child wrappers, not a local gesture surface.
    owner = _owner(masked, match.start())
    forwarded = {"child"}
    for declaration in re.finditer(r"\bWidget\??\s+(\w+)\s*(?=[;,)\]])", masked):
        if _owner(masked, declaration.start()) == owner:
            forwarded.add(declaration.group(1))
    while True:
        aliases = {m.group(1) for m in re.finditer(r"\b(?:final|var)\s+(\w+)\s*=\s*(?:widget\.)?(\w+)\s*;", masked)
                   if m.group(2) in forwarded and _owner(masked, m.start()) == owner} - forwarded
        if not aliases:
            break
        forwarded.update(aliases)
    forwarded_pattern = "|".join(re.escape(name) for name in sorted(forwarded))
    root_child = rf"(?:(?:widget\.)?(?:{forwarded_pattern})\b|MaterialApp\s*\(|Navigator\s*\(|Router\s*\()"
    if path != MAIN_DART and not re.match(root_child, named.get("child", ("", 0))[0]):
        return []
    if masked[match.start() : match.end()].startswith("NotificationListener"):
        if "<" in match.group() and not re.search(r"\b(?:Scroll\w*Notification|OverscrollNotification|UserScrollNotification|Notification|dynamic)\b", match.group()):
            return []  # domain events are not per-scroll/frame observation
        callback = r"onNotification"
    else:
        callback = r"onPointer(?:Down|Move|Hover|Signal|PanZoomUpdate)"
    positions = []
    for name, (value, position) in named.items():
        if not re.fullmatch(callback, name):
            continue
        if re.match(r"\s*\([^()]*\)\s*(?:=>\s*(?:false|true|null)\b|\{\s*(?:return\s+(?:false|true|null)\s*;\s*)?\})", value):
            continue  # literal no-op callback does no per-input work
        positions.append(position)
    return positions


HIGH_FREQUENCY_PROVIDER = r"(?:Capture|Sync|Conversation|Message|Episode|Device|VoiceRecorder)Provider"


def _unselected_provider_listener(text: str, match: re.Match[str]) -> bool:
    masked = _mask(text)
    before = masked[: match.start()]
    receiver = re.search(r"(\w+)\s*$", before)
    direct = re.search(rf"(?:read|of|watch)\s*<\s*{HIGH_FREQUENCY_PROVIDER}\s*>\s*\([^()]*\)\s*$", before)
    names = set(re.findall(rf"\b{HIGH_FREQUENCY_PROVIDER}\??\s+(\w+)", masked))
    for binding in re.finditer(r"\b(\w+)\s*=\s*([^;\n]+)", masked):
        if re.search(rf"\b{HIGH_FREQUENCY_PROVIDER}\b", binding.group(2)):
            names.add(binding.group(1))
    while True:
        aliases = {
            binding.group(1)
            for binding in re.finditer(r"\b(\w+)\s*=\s*(\w+)\s*;", masked)
            if binding.group(2) in names
        } - names
        if not aliases:
            break
        names.update(aliases)
    if not direct and (not receiver or receiver.group(1) not in names):
        return False
    receiver_name = receiver.group(1) if receiver else "context"
    start = match.end()
    span = None
    if masked[start:].lstrip().startswith("("):
        start += len(masked[start:]) - len(masked[start:].lstrip())
        close = _matching(masked, start, "(", ")")
        span = _body_span(masked, close + 1)
    else:
        callback = re.match(r"\s*(?:this\.)?(\w+)\b", masked[start:])
        if callback:
            span = next(iter(_resolve_declarations(masked, callback.group(1), match.start())), None)
    if span:
        body = masked[span[0] : span[1]]
        # Selection reads fields/records before comparing. An arbitrary helper
        # invocation before that comparison may itself walk history, so cannot
        # borrow an early return that follows it.
        work = next((call for call in re.finditer(r"\b(\w+)\s*\(", body) if call.group(1) not in {"if", "identical"}), None)
        if _guarded_before(body, work.start() if work else len(body), {receiver_name}):
            return False
    return True


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
        if re.search(r"!\s*(?:identical\b|\()|\)\s*(?:==\s*false\b|!=\s*true\b)|\bfalse\s*==\s*(?:identical\b|\()", condition):
            continue  # inverted equality returns on changes, not unchanged input
        if not any(re.search(rf"\b{re.escape(name)}\b", condition) for name in injected):
            continue
        # Compare the selected value and backing field in the SAME equality.
        # Merely mentioning both elsewhere in a condition can hide an unrelated test.
        atom = r"(?:this\.)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
        pairs = [(m.group(1), m.group(2)) for m in re.finditer(rf"({atom})\s*==\s*({atom})", condition)]
        pairs += [(m.group(1), m.group(2)) for m in re.finditer(rf"\bidentical\s*\(\s*({atom})\s*,\s*({atom})\s*\)", condition)]
        def root(value):
            return value.removeprefix("this.").split(".")[0]
        if not any((root(a) in injected and root(b) in stored) or (root(b) in injected and root(a) in stored)
                   for a, b in pairs):
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
        if name not in text:
            continue  # avoid lexing every app source again for each root hook
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


def check_semantics(root: Path) -> list[str]:
    """Absolute guard, including previously existing and unchanged source files."""
    problems = []
    for file in sorted((root / APP_ROOT).rglob("*.dart")):
        path = file.relative_to(root).as_posix()
        if not is_contract_source(path):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        if "ensureSemantics" not in text:
            continue
        if re.search(r"\bensureSemantics\s*\(", _mask(text)):
            for line in find_hits(text, path)["forced-semantics"]:
                problems.append(f"{path}:{line}: forced-semantics; use {fix_for('forced-semantics')}")
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

    semantics_problems = check_semantics(root)
    if semantics_problems:
        print("FAIL: INV-PERF-1 — ensureSemantics outside the explicit call allowlist (#23400).")
        for problem in semantics_problems:
            print(f"  - {problem}")

    if not args.changed_files:
        print("FAIL: --changed-files is required (or use --report / --graph).")
        return 1
    changed = [
        line.strip()
        for line in Path(args.changed_files).read_text(encoding="utf-8").splitlines()
        if line.strip() and is_contract_source(line.strip())
    ]
    if not changed:
        if graph_problems:
            _print_graph_failure(graph_problems)
        if semantics_problems or graph_problems:
            return 1
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

    failed = bool(semantics_problems)
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
