#!/usr/bin/env python3
"""Verify the SF Symbols -> Material Symbols Rounded map (design/.../SFSymbols.kt).

Checks:
  1. every SF Symbol name used by the iOS app (omi-native) has an entry in SF_SYMBOLS,
  2. every mapped target ligature exists in material_symbols_rounded.codepoints.

Usage:
  check_symbols.py                         run the checks (exit 1 on failure)
  check_symbols.py --list-used             print the SF names found in omi-native
  check_symbols.py --subset IN.ttf OUT.ttf run the checks, then print the ligature names
                                           needed for a later pyftsubset step (not run here)

Options:
  --ios-root PATH   the iOS app (default: $OMI_NATIVE_ROOT, else ../ios, else ~/CODING/omi-native)
  --strict          also fail on map entries no longer used by the iOS app

Extraction rules (kept in sync with how omi-native stores symbol names):
  * all *.swift under App, Packages, Extensions, Watch; skips .build, .claude (worktrees),
    Tests and Generated directories and whole-line // comments,
  * every double-quoted string literal is a candidate (this catches systemImage:, systemName:,
    Image(systemName:), Label(..., systemImage:) and names routed through vars, enums, switches
    and arrays such as `symbol: "mic"` or `case .x: "bell"`),
  * a candidate counts only if it is a real SF Symbol name according to macOS CoreGlyphs
    (name_availability.plist + name_aliases.strings); off macOS the vocabulary falls back to the
    names already in the map plus literals passed directly to systemName:/systemImage:,
  * undotted names are dropped in obviously non-symbol positions (L("..."), String(localized:),
    subscripts ["..."], dictionary keys "...":, string case labels case "...") and when listed
    in NOT_SYMBOLS (plain words that collide with SF names, verified by hand).
"""
from __future__ import annotations

import os
import plistlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANDROID_ROOT = HERE.parent.parent
KT_FILE = ANDROID_ROOT / "design/src/main/kotlin/com/friend/ios/design/SFSymbols.kt"
CODEPOINTS = HERE / "material_symbols_rounded.codepoints"
CORE_GLYPHS = Path("/System/Library/CoreServices/CoreGlyphs.bundle/Contents/Resources")

SCAN_DIRS = ("App", "Packages", "Extensions", "Watch")
SKIP_DIRS = {".build", ".claude", "Tests", "Generated", "DerivedData", "build"}

# Plain words in omi-native that happen to be SF Symbol names but are never rendered as icons
# (keyword lists, ids, JSON keys, localization keys). Checked by hand against call sites.
NOT_SYMBOLS = {
    "a", "app", "at", "document", "drop", "eyebrow", "figure", "forward", "level", "mail",
    "memories", "microphone", "numbers", "play", "right", "scope", "siri", "sleep", "speaker",
    "target", "ticket", "translate",
}

LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
DIRECT = re.compile(r'(?:systemName|systemImage)\s*:\s*"([^"\\]+)"')


def load_sf_vocabulary(fallback: set[str]) -> set[str] | None:
    plist = CORE_GLYPHS / "name_availability.plist"
    if not plist.exists():
        return None
    with plist.open("rb") as fh:
        names = set(plistlib.load(fh)["symbols"])
    aliases = CORE_GLYPHS / "name_aliases.strings"
    if aliases.exists():
        text = aliases.read_text(encoding="utf-8", errors="ignore")
        names |= {m.group(1) for m in re.finditer(r'"([^"]+)"\s*=\s*"[^"]+"', text)}
    return names


def non_symbol_position(line: str, start: int, end: int) -> bool:
    before = line[:start].rstrip()
    after = line[end:].lstrip()
    if re.search(r'(?:\bL|String\(localized:|NSLocalizedString)\s*\(\s*$', before):
        return True
    if before.endswith("[") and after.startswith("]"):
        return True
    if after.startswith(":") and not after.startswith("::"):
        return True  # dictionary key or case label
    if re.search(r'\bcase\s*$', before) or re.search(r'\bcase\b[^:]*,\s*$', before):
        return True
    return False


def extract_used(ios_root: Path, mapped: set[str]) -> dict[str, list[str]]:
    vocab = load_sf_vocabulary(mapped)
    used: dict[str, list[str]] = {}
    for top in SCAN_DIRS:
        base = ios_root / top
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith(".swift"):
                    continue
                path = Path(dirpath) / fn
                rel = str(path.relative_to(ios_root))
                for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if line.lstrip().startswith("//"):
                        continue
                    direct = {m.group(1) for m in DIRECT.finditer(line)}
                    for m in LITERAL.finditer(line):
                        name = m.group(1)
                        if vocab is not None:
                            if name not in vocab:
                                continue
                        elif name not in mapped and name not in direct:
                            continue
                        if "." not in name:
                            if name in NOT_SYMBOLS:
                                continue
                            if non_symbol_position(line, m.start(), m.end()):
                                continue
                        used.setdefault(name, []).append(f"{rel}:{lineno}")
    return used


def parse_map(path: Path) -> dict[str, tuple[str, bool]]:
    text = path.read_text(encoding="utf-8")
    entries: dict[str, tuple[str, bool]] = {}
    pat = re.compile(r'"([^"]+)"\s+to\s+SymbolGlyph\(\s*"([^"]+)"\s*,\s*(true|false)\s*\)')
    for m in pat.finditer(text):
        if m.group(1) in entries:
            raise SystemExit(f"duplicate key in {path.name}: {m.group(1)}")
        entries[m.group(1)] = (m.group(2), m.group(3) == "true")
    return entries


def load_codepoints(path: Path) -> set[str]:
    return {line.split()[0] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def main(argv: list[str]) -> int:
    args = list(argv)
    beside = Path(__file__).resolve().parents[3] / "ios"
    ios_root = Path(os.environ.get("OMI_NATIVE_ROOT", beside if beside.is_dir() else "~/CODING/omi-native")).expanduser()
    strict = False
    subset: tuple[str, str] | None = None
    list_used = False
    while args:
        a = args.pop(0)
        if a == "--ios-root":
            ios_root = Path(args.pop(0)).expanduser()
        elif a == "--strict":
            strict = True
        elif a == "--list-used":
            list_used = True
        elif a == "--subset":
            if len(args) < 2:
                print("--subset needs IN.ttf OUT.ttf", file=sys.stderr)
                return 2
            subset = (args.pop(0), args.pop(0))
        else:
            print(__doc__, file=sys.stderr)
            return 2

    mapping = parse_map(KT_FILE) if KT_FILE.exists() else {}
    codepoints = load_codepoints(CODEPOINTS)
    used = extract_used(ios_root, set(mapping))

    if list_used:
        for name in sorted(used):
            print(name)
        return 0

    errors: list[str] = []
    for name in sorted(set(used) - set(mapping)):
        errors.append(f"unmapped SF symbol: {name}  (first use {used[name][0]})")
    for sf, (target, _) in sorted(mapping.items()):
        if target not in codepoints:
            errors.append(f"target not in codepoints: {sf} -> {target}")
    keys = list(mapping)
    if keys != sorted(keys):
        errors.append("SF_SYMBOLS entries are not sorted alphabetically by SF name")
    unused = sorted(set(mapping) - set(used))
    if strict:
        errors += [f"mapped but unused: {n}" for n in unused]

    targets = sorted({t for t, _ in mapping.values()})
    print(f"used SF symbols: {len(used)}  mapped: {len(mapping)}  distinct ligatures: {len(targets)}"
          f"  codepoints: {len(codepoints)}")
    if unused and not strict:
        print(f"note: {len(unused)} mapped but unused: {', '.join(unused)}")
    if errors:
        for e in errors:
            print("ERROR", e)
        return 1
    print("OK")

    if subset:
        src, dst = subset
        print(f"# ligatures needed to subset {src} -> {dst}:")
        for t in targets:
            print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
