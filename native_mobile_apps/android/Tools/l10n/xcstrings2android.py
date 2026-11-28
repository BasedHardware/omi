#!/usr/bin/env python3
"""Localizable.xcstrings (omi-native) -> Android res/values-*/strings.xml (:design).

The iOS catalog is already the merged result of the Flutter ARB files and native.json, limited to
the keys the app uses, so converting it keeps both apps on identical keys and translations.
Key `a.b` becomes resource `a__b` (Android names allow [A-Za-z0-9_] only); `L("a.b")` maps it back.

Usage: xcstrings2android.py [--xcstrings PATH] [--res DIR] [--check]
"""
import argparse
import json
import pathlib
import re
import sys
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _main_checkout(root: pathlib.Path) -> pathlib.Path:
    """A linked worktree's `.git` is a file `gitdir: <main>/.git/worktrees/<name>`, wherever it lives."""
    git = root / ".git"
    if git.is_file():
        return pathlib.Path(git.read_text().split("gitdir:", 1)[1].strip()).parents[2]
    return root


# Inside the Omi repository the iOS app sits next to this one (`../ios`) and the Flutter app two
# levels up; in separate checkouts they are the sibling repos omi-native and omi-fresh (next to the
# main checkout, also when run from a worktree).
CODING = _main_checkout(ROOT).parent
IOS = ROOT.parent / "ios" if (ROOT.parent / "ios").is_dir() else CODING / "omi-native"
UPSTREAM = ROOT.parents[1] if (ROOT.parents[1] / "backend").is_dir() else CODING / "omi-fresh"
DEFAULT_XC = IOS / "Packages/OmiDesign/Sources/OmiDesign/Resources/Localizable.xcstrings"
DEFAULT_RES = ROOT / "design/src/main/res"
DEFAULT_ARB = UPSTREAM / "app/lib/l10n"
DEFAULT_NATIVE = IOS / "Tools/l10n/native.json"
KEY_USE = re.compile(r'\bL\(\s*"([A-Za-z0-9_.]+)"')
FOLDER = {"en": "values", "he": "values-iw", "id": "values-in", "no": "values-nb", "tl": "values-fil"}


def resource_name(key: str) -> str:
    name = key.replace(".", "__")
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return "_" + name if name[0].isdigit() else name


def android_value(value: str) -> str:
    # %1$@ -> %1$s, %@ -> %s; %% stays.
    value = re.sub(r"%(\d+\$)?@", lambda m: "%" + (m.group(1) or "") + "s", value)
    value = escape(value)
    value = value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
    if value[:1] in ("@", "?"):
        value = "\\" + value
    # aapt trims leading/trailing spaces ("By continuing, you agree to our "); quoting keeps them.
    if value != value.strip(" "):
        value = '"' + value + '"'
    return value


def android_only_keys(known: set[str]) -> set[str]:
    """Keys the Kotlin code uses that iOS doesn't (e.g. `memoryThisPhone`): taken from the ARB files."""
    used = set()
    for path in ROOT.glob("*/src/**/*.kt"):
        used |= set(KEY_USE.findall(path.read_text(errors="ignore")))
    return used - known


def positional(value: str) -> str:
    """{name} placeholders -> positional %N$@, in order of first appearance (arb2xcstrings rule)."""
    names = list(dict.fromkeys(re.findall(r"\{(\w+)\}", value)))
    value = value.replace("%", "%%") if names else value
    for i, name in enumerate(names, 1):
        value = value.replace("{" + name + "}", f"%{i}$@")
    return value


def load_native(path: pathlib.Path, keys: set[str]) -> dict[str, dict]:
    """omi-native's native.json ({key: {locale: value}}) for keys iOS no longer uses but Kotlin still does."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {
        key: {"localizations": {loc: {"stringUnit": {"value": positional(v)}} for loc, v in data[key].items()}}
        for key in keys if key in data
    }


def load_arb(arb_dir: pathlib.Path, keys: set[str]) -> dict[str, dict]:
    """{key: {"localizations": {locale: {"stringUnit": {"value": ...}}}}} for ARB keys, xcstrings-shaped."""
    out: dict[str, dict] = {}
    for path in sorted(arb_dir.glob("app_*.arb")):
        locale = path.stem[len("app_"):]
        data = json.loads(path.read_text())
        for key in keys:
            value = data.get(key)
            if isinstance(value, str):
                value = positional(value)
                out.setdefault(key, {"localizations": {}})["localizations"][locale] = {"stringUnit": {"value": value}}
    return out


def build(xc_path: pathlib.Path, arb_dir: pathlib.Path = DEFAULT_ARB, native_path: pathlib.Path = DEFAULT_NATIVE) -> dict[str, str]:
    catalog = json.loads(xc_path.read_text())
    extra = android_only_keys(set(catalog["strings"]))
    missing = []
    if extra:
        arb = load_arb(arb_dir, extra)
        native = load_native(native_path, extra - set(arb))
        catalog["strings"].update(arb)
        catalog["strings"].update(native)
        missing = sorted(extra - set(arb) - set(native))
    if missing:
        print("keys used in Kotlin but in neither catalog nor ARB: " + ", ".join(missing), file=sys.stderr)
    source = catalog["sourceLanguage"]
    per_locale: dict[str, dict[str, str]] = {}
    for key, entry in sorted(catalog["strings"].items()):
        locs = entry.get("localizations", {})
        for locale, loc in locs.items():
            unit = loc.get("stringUnit")
            if unit and unit.get("value") is not None:
                per_locale.setdefault(locale, {})[key] = unit["value"]
        # A key without an English unit renders as itself on iOS (`value: key`).
        per_locale.setdefault(source, {}).setdefault(key, key)
    files = {}
    for locale, strings in sorted(per_locale.items()):
        folder = FOLDER.get(locale, f"values-{locale}")
        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 "<!-- Generated by Tools/l10n/xcstrings2android.py from omi-native Localizable.xcstrings. Do not edit. -->",
                 '<resources xmlns:tools="http://schemas.android.com/tools" tools:ignore="MissingTranslation,ExtraTranslation,TypographyEllipsis">']
        for key, value in strings.items():
            formatted = "" if re.search(r"%(\d+\$)?[s@d]", value) else ' formatted="false"'
            lines.append(f'    <string name="{resource_name(key)}"{formatted}>{android_value(value)}</string>')
        lines.append("</resources>")
        files[f"{folder}/strings.xml"] = "\n".join(lines) + "\n"
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xcstrings", type=pathlib.Path, default=DEFAULT_XC)
    ap.add_argument("--res", type=pathlib.Path, default=DEFAULT_RES)
    ap.add_argument("--arb", type=pathlib.Path, default=DEFAULT_ARB, help="the Flutter app's ARB folder (Android-only keys)")
    ap.add_argument("--native", type=pathlib.Path, default=DEFAULT_NATIVE,
                    help="native.json for keys not yet in the catalog (e.g. an omi-native branch's copy)")
    ap.add_argument("--check", action="store_true", help="fail when the generated files are stale")
    args = ap.parse_args()
    files = build(args.xcstrings, arb_dir=args.arb, native_path=args.native)
    stale = []
    for rel, text in files.items():
        path = args.res / rel
        if path.exists() and path.read_text() == text:
            continue
        stale.append(rel)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if args.check and stale:
        print(f"stale: {len(stale)} files (run Tools/l10n/xcstrings2android.py)", file=sys.stderr)
        return 1
    print(f"{len(files)} locales, {'up to date' if not stale else f'{len(stale)} written'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
