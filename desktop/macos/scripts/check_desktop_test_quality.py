#!/usr/bin/env python3
"""Guard Swift collection construction and keep brittle desktop tests from growing.

The checker enforces three lessons from recurring macOS bug fixes:

1. `Dictionary(uniqueKeysWithValues:)` is a process-terminating assertion when
   external or persisted data contains a duplicate key. Production code must use
   an explicit collision policy such as `Dictionary(lastWriteWins:)`.
2. Tests that read production source and assert on strings do not exercise
   behavior. Existing debt is ratcheted, while new static-contract tripwires need
   a narrow, reasoned annotation.
3. Wall-clock sleeps make tests timing-dependent. Existing debt is ratcheted;
   new tests should inject a clock, await a signal, or annotate an unavoidable
   integration wait with a reason.

Escapes are deliberately local (same line or immediately preceding line):

  // omi-collection-safety: static-unique-keys -- enum cases are unique by construction
  Dictionary(uniqueKeysWithValues: SomeEnum.allCases.map { ($0, value($0)) })

  // omi-test-quality: source-inspection -- static contract: forbids a legacy symbol
  let source = try String(contentsOf: productionSource)

  // omi-test-quality: wall-clock-wait -- exercises the real scheduler integration
  try await Task.sleep(for: .milliseconds(10))

The collection escape is only for uniqueness proven by a static type contract.
The source-inspection escape is only for forbidden-pattern/static wiring
tripwires, never as a substitute for behavioral coverage.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

COLLECTION_ROOT = "desktop/macos/Desktop/Sources"
TEST_ROOT = "desktop/macos/Desktop/Tests"

# Pinned debt ceilings. These may only decrease. Escaped sites are not counted.
# Run with --print after improving tests, then lower both relevant values.
SOURCE_INSPECTION_FILE_BASELINE = 57
SOURCE_INSPECTION_SITE_BASELINE = 165
WALL_CLOCK_WAIT_BASELINE = 19

MIN_REASON_LENGTH = 12

COLLECTION_ANNOTATION_RE = re.compile(r"//\s*omi-collection-safety:\s*static-unique-keys(?:\s*--\s*(.*?))?\s*$")
SOURCE_ANNOTATION_RE = re.compile(r"//\s*omi-test-quality:\s*source-inspection(?:\s*--\s*(.*?))?\s*$")
WAIT_ANNOTATION_RE = re.compile(r"//\s*omi-test-quality:\s*wall-clock-wait(?:\s*--\s*(.*?))?\s*$")

STRING_READ_RE = re.compile(r"\bString\s*\(\s*contentsOf(?:File)?\s*:", re.MULTILINE)
WALL_CLOCK_WAIT_RE = re.compile(
    r"\b(?:Task(?:\s*<[^>{}\n]+>)?\.sleep|Thread\.sleep|Darwin\.sleep|Glibc\.sleep|usleep)\s*\(",
    re.MULTILINE,
)
FUNCTION_RE = re.compile(r"\bfunc\s+(`?[A-Za-z_][A-Za-z0-9_]*`?)\s*(?:<[^>{}]*>)?\s*\(")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[<>()\[\]:,.]")


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    line: int
    excerpt: str
    message: str


@dataclass(frozen=True)
class FunctionSpan:
    name: str
    start: int
    end: int


@dataclass(frozen=True)
class ScanReport:
    collection_findings: tuple[Finding, ...]
    source_findings: tuple[Finding, ...]
    wait_findings: tuple[Finding, ...]
    annotation_findings: tuple[Finding, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="Repository root (default: inferred from this script).")
    parser.add_argument(
        "--print",
        dest="print_findings",
        action="store_true",
        help="Print every counted site and current totals without enforcing baselines.",
    )
    return parser.parse_args()


def repo_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    return Path(__file__).resolve().parents[3]


def _mask_non_code(text: str) -> str:
    """Replace Swift comments and string contents with spaces, preserving offsets."""

    chars = list(text)
    index = 0
    length = len(chars)
    state = "code"
    block_depth = 0
    string_hashes = 0
    multiline = False

    def mask(position: int) -> None:
        if chars[position] != "\n":
            chars[position] = " "

    while index < length:
        if state == "code":
            if index + 1 < length and chars[index] == "/" and chars[index + 1] == "/":
                mask(index)
                mask(index + 1)
                index += 2
                state = "line_comment"
                continue
            if index + 1 < length and chars[index] == "/" and chars[index + 1] == "*":
                mask(index)
                mask(index + 1)
                index += 2
                block_depth = 1
                state = "block_comment"
                continue

            hash_count = 0
            while index + hash_count < length and chars[index + hash_count] == "#":
                hash_count += 1
            quote = index + hash_count
            if quote < length and chars[quote] == '"':
                string_hashes = hash_count
                multiline = text.startswith('"""', quote)
                opening_length = hash_count + (3 if multiline else 1)
                for position in range(index, min(length, index + opening_length)):
                    mask(position)
                index += opening_length
                state = "string"
                continue
            index += 1
            continue

        if state == "line_comment":
            if chars[index] == "\n":
                state = "code"
            else:
                mask(index)
            index += 1
            continue

        if state == "block_comment":
            if index + 1 < length and text[index : index + 2] == "/*":
                mask(index)
                mask(index + 1)
                index += 2
                block_depth += 1
                continue
            if index + 1 < length and text[index : index + 2] == "*/":
                mask(index)
                mask(index + 1)
                index += 2
                block_depth -= 1
                if block_depth == 0:
                    state = "code"
                continue
            mask(index)
            index += 1
            continue

        closing_quote = '"""' if multiline else '"'
        closing = closing_quote + ("#" * string_hashes)
        if text.startswith(closing, index):
            for position in range(index, min(length, index + len(closing))):
                mask(position)
            index += len(closing)
            state = "code"
            continue
        if string_hashes == 0 and not multiline and chars[index] == "\\":
            mask(index)
            if index + 1 < length:
                mask(index + 1)
            index += 2
            continue
        mask(index)
        index += 1

    return "".join(chars)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_excerpt(lines: list[str], line: int) -> str:
    return lines[line - 1].strip() if 0 < line <= len(lines) else ""


def _matching_brace(masked: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(masked)


def _function_spans(masked: str) -> list[FunctionSpan]:
    spans: list[FunctionSpan] = []
    for match in FUNCTION_RE.finditer(masked):
        opening = masked.find("{", match.end())
        if opening == -1:
            continue
        spans.append(FunctionSpan(match.group(1).strip("`"), match.start(), _matching_brace(masked, opening)))
    return spans


def _enclosing_function(spans: list[FunctionSpan], offset: int) -> FunctionSpan | None:
    candidates = [span for span in spans if span.start <= offset < span.end]
    return max(candidates, key=lambda span: span.start, default=None)


def _annotation_line(lines: list[str], line: int, annotation_re: re.Pattern[str]) -> tuple[int, re.Match[str]] | None:
    for candidate in (line, line - 1):
        if candidate <= 0 or candidate > len(lines):
            continue
        match = annotation_re.search(lines[candidate - 1])
        if match:
            return candidate, match
    return None


def _annotation_allows(
    lines: list[str],
    line: int,
    annotation_re: re.Pattern[str],
    *,
    require_static_contract: bool,
    path: str,
) -> tuple[bool, Finding | None]:
    annotated = _annotation_line(lines, line, annotation_re)
    if annotated is None:
        return False, None
    annotation_line, match = annotated
    reason = (match.group(1) or "").strip()
    if require_static_contract:
        prefix = "static contract:"
        valid = reason.lower().startswith(prefix) and len(reason[len(prefix) :].strip()) >= MIN_REASON_LENGTH
        expectation = f"a '{prefix}' reason of at least {MIN_REASON_LENGTH} characters"
    else:
        valid = len(reason) >= MIN_REASON_LENGTH
        expectation = f"a reason of at least {MIN_REASON_LENGTH} characters"
    if valid:
        return True, None
    return False, Finding(
        category="invalid-annotation",
        path=path,
        line=annotation_line,
        excerpt=_line_excerpt(lines, annotation_line),
        message=f"escape annotation requires {expectation}",
    )


def _raw_dictionary_offsets(masked: str) -> list[int]:
    tokens = [(match.group(0), match.start()) for match in TOKEN_RE.finditer(masked)]
    offsets: set[int] = set()
    for index, (token, offset) in enumerate(tokens):
        if token != "Dictionary":
            continue
        cursor = index + 1
        if cursor < len(tokens) and tokens[cursor][0] == "<":
            depth = 0
            while cursor < len(tokens):
                if tokens[cursor][0] == "<":
                    depth += 1
                elif tokens[cursor][0] == ">":
                    depth -= 1
                    if depth == 0:
                        cursor += 1
                        break
                cursor += 1
        if cursor + 1 < len(tokens) and tokens[cursor][0] == "." and tokens[cursor + 1][0] == "init":
            cursor += 2
        if cursor + 2 >= len(tokens) or tokens[cursor][0] != "(":
            continue
        if tokens[cursor + 1][0] == "uniqueKeysWithValues" and tokens[cursor + 2][0] == ":":
            offsets.add(offset)

    inferred_init = re.compile(r"\.\s*init\s*\(\s*uniqueKeysWithValues\s*:")
    for match in inferred_init.finditer(masked):
        line_start = masked.rfind("\n", 0, match.start()) + 1
        if any(line_start <= offset < match.start() for offset in offsets):
            continue
        offsets.add(match.start())
    return sorted(offsets)


def _looks_like_production_source_read(text: str, span: FunctionSpan | None, offset: int) -> bool:
    if span is None:
        context_start = max(0, offset - 800)
        context_end = min(len(text), offset + 800)
        name = ""
    else:
        context_start = span.start
        context_end = span.end
        name = span.name.lower()
    context = text[context_start:context_end]

    if "source" in name:
        return True
    if re.search(r'(?:Sources(?:/|")|[A-Za-z0-9_+.-]+\.swift\b)', context):
        return True
    if "#filePath" in context and re.search(r"\b(?:source|implementation|wiring)\w*\b", context, re.IGNORECASE):
        return True
    if "#filePath" in context and "deletingLastPathComponent" in context and ".contains(" in context:
        return True
    return False


def scan_swift_file(path: Path, *, relative_path: str, role: str) -> ScanReport:
    text = path.read_text(encoding="utf-8")
    masked = _mask_non_code(text)
    lines = text.splitlines()
    collection_findings: list[Finding] = []
    source_findings: list[Finding] = []
    wait_findings: list[Finding] = []
    annotation_findings: list[Finding] = []

    if role == "production":
        for offset in _raw_dictionary_offsets(masked):
            line = _line_number(text, offset)
            allowed, invalid = _annotation_allows(
                lines,
                line,
                COLLECTION_ANNOTATION_RE,
                require_static_contract=False,
                path=relative_path,
            )
            if invalid is not None:
                annotation_findings.append(invalid)
            if not allowed:
                collection_findings.append(
                    Finding(
                        category="unsafe-collection",
                        path=relative_path,
                        line=line,
                        excerpt=_line_excerpt(lines, line),
                        message="raw uniqueKeysWithValues initializer can trap on duplicate data",
                    )
                )

    if role == "test":
        spans = _function_spans(masked)
        for match in STRING_READ_RE.finditer(masked):
            if not _looks_like_production_source_read(text, _enclosing_function(spans, match.start()), match.start()):
                continue
            line = _line_number(text, match.start())
            allowed, invalid = _annotation_allows(
                lines,
                line,
                SOURCE_ANNOTATION_RE,
                require_static_contract=True,
                path=relative_path,
            )
            if invalid is not None:
                annotation_findings.append(invalid)
            if not allowed:
                source_findings.append(
                    Finding(
                        category="source-inspection",
                        path=relative_path,
                        line=line,
                        excerpt=_line_excerpt(lines, line),
                        message="test reads production source instead of exercising behavior",
                    )
                )

        for match in WALL_CLOCK_WAIT_RE.finditer(masked):
            line = _line_number(text, match.start())
            allowed, invalid = _annotation_allows(
                lines,
                line,
                WAIT_ANNOTATION_RE,
                require_static_contract=False,
                path=relative_path,
            )
            if invalid is not None:
                annotation_findings.append(invalid)
            if not allowed:
                wait_findings.append(
                    Finding(
                        category="wall-clock-wait",
                        path=relative_path,
                        line=line,
                        excerpt=_line_excerpt(lines, line),
                        message="test waits on wall-clock time instead of an injected clock or signal",
                    )
                )

    return ScanReport(
        collection_findings=tuple(collection_findings),
        source_findings=tuple(source_findings),
        wait_findings=tuple(wait_findings),
        annotation_findings=tuple(annotation_findings),
    )


def scan_repository(root: Path) -> ScanReport:
    collection_root = root / COLLECTION_ROOT
    test_root = root / TEST_ROOT
    missing = [str(path) for path in (collection_root, test_root) if not path.is_dir()]
    if missing:
        raise RuntimeError(f"scan root not found: {', '.join(missing)}")

    reports: list[ScanReport] = []
    for path in sorted(collection_root.rglob("*.swift")):
        reports.append(scan_swift_file(path, relative_path=path.relative_to(root).as_posix(), role="production"))
    for path in sorted(test_root.rglob("*.swift")):
        reports.append(scan_swift_file(path, relative_path=path.relative_to(root).as_posix(), role="test"))

    return ScanReport(
        collection_findings=tuple(finding for report in reports for finding in report.collection_findings),
        source_findings=tuple(finding for report in reports for finding in report.source_findings),
        wait_findings=tuple(finding for report in reports for finding in report.wait_findings),
        annotation_findings=tuple(finding for report in reports for finding in report.annotation_findings),
    )


def _print_findings(findings: tuple[Finding, ...]) -> None:
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.category}: {finding.excerpt}")


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    try:
        report = scan_repository(root)
    except (OSError, UnicodeDecodeError, RuntimeError) as exc:
        print(f"FAIL: desktop quality scan could not run: {exc}", file=sys.stderr)
        return 2

    source_files = len({finding.path for finding in report.source_findings})
    source_sites = len(report.source_findings)
    wait_sites = len(report.wait_findings)

    if args.print_findings:
        _print_findings(report.collection_findings)
        _print_findings(report.source_findings)
        _print_findings(report.wait_findings)
        _print_findings(report.annotation_findings)
        print(
            "\n"
            f"unsafe collection initializers: {len(report.collection_findings)}\n"
            f"production-source inspection: {source_files} files / {source_sites} sites "
            f"(baselines {SOURCE_INSPECTION_FILE_BASELINE} / {SOURCE_INSPECTION_SITE_BASELINE})\n"
            f"wall-clock waits: {wait_sites} (baseline {WALL_CLOCK_WAIT_BASELINE})\n"
            f"invalid annotations: {len(report.annotation_findings)}"
        )
        return 0

    failed = False
    if report.collection_findings:
        failed = True
        print("FAIL: production Swift contains trapping dictionary initializers:", file=sys.stderr)
        _print_findings(report.collection_findings)
        print(
            "Use Dictionary(lastWriteWins:) for data-driven collections. The static-unique-keys "
            "escape is reserved for uniqueness enforced by a type contract.",
            file=sys.stderr,
        )
    if report.annotation_findings:
        failed = True
        print("FAIL: malformed desktop quality escape annotations:", file=sys.stderr)
        for finding in report.annotation_findings:
            print(f"{finding.path}:{finding.line}: {finding.message}: {finding.excerpt}", file=sys.stderr)
    if source_files > SOURCE_INSPECTION_FILE_BASELINE or source_sites > SOURCE_INSPECTION_SITE_BASELINE:
        failed = True
        print(
            "FAIL: production-source inspection in Swift tests rose to "
            f"{source_files} files / {source_sites} sites "
            f"(baselines {SOURCE_INSPECTION_FILE_BASELINE} / {SOURCE_INSPECTION_SITE_BASELINE}).",
            file=sys.stderr,
        )
        print(
            "Exercise the production API behavior. For a genuine forbidden-pattern/static "
            "contract only, add a local reasoned source-inspection annotation.",
            file=sys.stderr,
        )
    if wait_sites > WALL_CLOCK_WAIT_BASELINE:
        failed = True
        print(
            f"FAIL: wall-clock waits in Swift tests rose to {wait_sites} " f"(baseline {WALL_CLOCK_WAIT_BASELINE}).",
            file=sys.stderr,
        )
        print(
            "Inject a Clock/sleeper or await a deterministic signal. Annotate only an "
            "unavoidable integration wait and include the reason.",
            file=sys.stderr,
        )
    if failed:
        print(
            "See counted sites with: python3 desktop/macos/scripts/check_desktop_test_quality.py --print",
            file=sys.stderr,
        )
        return 1

    notes: list[str] = []
    if source_files < SOURCE_INSPECTION_FILE_BASELINE or source_sites < SOURCE_INSPECTION_SITE_BASELINE:
        notes.append(
            "source-inspection debt fell; lower SOURCE_INSPECTION_FILE_BASELINE and " "SOURCE_INSPECTION_SITE_BASELINE"
        )
    if wait_sites < WALL_CLOCK_WAIT_BASELINE:
        notes.append("wall-clock-wait debt fell; lower WALL_CLOCK_WAIT_BASELINE")
    if notes:
        print("NOTE: " + "; ".join(notes) + ".")
    print(
        "OK: no trapping dictionary initializers; desktop test-quality debt at or below "
        f"baseline ({source_files} source-reading files / {source_sites} sites, {wait_sites} waits)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
