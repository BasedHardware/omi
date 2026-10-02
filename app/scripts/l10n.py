#!/usr/bin/env python3
"""One-command localization for the Flutter app.

Add, change, or remove a key across every locale ARB file, then regenerate.
The calling agent supplies translations; this tool never calls a network or
model. From app/: ``python3 scripts/l10n.py <add|set|remove|template|check>``.

Writes are atomic: validation runs first, and any later failure restores the
previous ARB and generated Dart bytes. Re-running a completed add/set/remove
with identical input is a no-op.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

KEY_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
ARB_NAME_RE = re.compile(r"^app_([A-Za-z0-9_]+)\.arb$")
IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
class L10nError(Exception):
    """User-facing failure; message is printed and the process exits 1."""


def dump_arb(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=4, ensure_ascii=False) + "\n"


def message_keys(data: dict[str, Any]) -> set[str]:
    return {k for k in data if not str(k).startswith("@")}


def locale_from_arb_path(path: Path) -> str:
    match = ARB_NAME_RE.fullmatch(path.name)
    if not match:
        raise L10nError(f"unexpected ARB filename: {path.name}")
    return match.group(1)


def discover_arb_files(arb_dir: Path) -> dict[str, Path]:
    files = sorted(p for p in arb_dir.glob("app_*.arb") if p.is_file())
    if not files:
        raise L10nError(f"no app_*.arb files in {arb_dir}")
    by_locale: dict[str, Path] = {}
    for path in files:
        locale = locale_from_arb_path(path)
        if locale in by_locale:
            raise L10nError(f"duplicate locale {locale}: {by_locale[locale].name} and {path.name}")
        by_locale[locale] = path
    if "en" not in by_locale:
        raise L10nError(f"template app_en.arb is missing from {arb_dir}")
    return by_locale


def load_arb(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L10nError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise L10nError(f"{path.name} must be a JSON object")
    return data


def load_all_arbs(by_locale: dict[str, Path]) -> dict[str, dict[str, Any]]:
    return {locale: load_arb(path) for locale, path in by_locale.items()}


# --- ICU -------------------------------------------------------------------


class _Cursor:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    def remaining(self) -> str:
        return self.text[self.i :]

    def peek(self) -> str:
        return self.text[self.i] if self.i < len(self.text) else ""

    def eof(self) -> bool:
        return self.i >= len(self.text)


def _skip_quoted(cur: _Cursor) -> str:
    """Consume an ICU quoted literal starting at the current quote. Returns text including quotes."""
    start = cur.i
    cur.i += 1
    if cur.peek() == "'":
        cur.i += 1
        return cur.text[start : cur.i]
    while not cur.eof() and cur.peek() != "'":
        cur.i += 1
    if cur.peek() == "'":
        cur.i += 1
    return cur.text[start : cur.i]


def parse_icu(message: str, use_escaping: bool = False) -> list[Any]:
    """Parse an ICU message into a structure that ignores literal text.

    A simple ``{name}`` becomes ``("ph", name)``. ``{name, plural, =1{...} other{...}}``
    becomes ``("plural", name, ((selector, nested), ...))``. Parse failures raise
    ``L10nError``.

    Apostrophes are ICU quotes only when ``use_escaping`` is true, matching Flutter
    gen-l10n's ``use-escaping`` (default false). With escaping off, ``What's New in
    {version}`` still has a ``version`` placeholder.
    """
    return _parse_message(_Cursor(message), stop_on_brace=False, use_escaping=use_escaping)


def _parse_message(cur: _Cursor, stop_on_brace: bool, use_escaping: bool) -> list[Any]:
    nodes: list[Any] = []
    while not cur.eof():
        ch = cur.peek()
        if stop_on_brace and ch == "}":
            break
        if ch == "'" and use_escaping:
            _skip_quoted(cur)
            continue
        if ch == "{":
            nodes.append(_parse_argument(cur, use_escaping))
            continue
        cur.i += 1
    return nodes


def _parse_argument(cur: _Cursor, use_escaping: bool) -> Any:
    if cur.peek() != "{":
        raise L10nError(f"expected '{{' in ICU message at index {cur.i}")
    cur.i += 1
    _skip_ws(cur)
    name = _parse_ident(cur)
    _skip_ws(cur)
    if cur.peek() == "}":
        cur.i += 1
        return ("ph", name)
    if cur.peek() != ",":
        raise L10nError(f"malformed ICU placeholder '{{{name}'")
    cur.i += 1
    _skip_ws(cur)
    kind = _parse_ident(cur)
    _skip_ws(cur)
    if kind in {"plural", "select"}:
        if cur.peek() == ",":
            cur.i += 1
            _skip_ws(cur)
        options = _parse_options(cur, use_escaping)
        if cur.peek() != "}":
            raise L10nError(f"unclosed ICU {kind} '{{{name}'")
        cur.i += 1
        return (kind, name, tuple(options))
    # {name, number} / {name, date, ...} — consume until matching close
    while not cur.eof() and cur.peek() != "}":
        if cur.peek() == "{":
            _parse_argument(cur, use_escaping)
        elif cur.peek() == "'" and use_escaping:
            _skip_quoted(cur)
        else:
            cur.i += 1
    if cur.peek() != "}":
        raise L10nError(f"unclosed ICU placeholder '{{{name}'")
    cur.i += 1
    return ("typed", name, kind)


def _parse_options(cur: _Cursor, use_escaping: bool) -> list[tuple[str, tuple[Any, ...]]]:
    options: list[tuple[str, tuple[Any, ...]]] = []
    while not cur.eof() and cur.peek() != "}":
        _skip_ws(cur)
        if cur.peek() == "}":
            break
        selector = _parse_selector(cur)
        _skip_ws(cur)
        if cur.peek() != "{":
            raise L10nError(f"ICU plural/select selector {selector!r} is missing a body")
        cur.i += 1
        body = _parse_message(cur, stop_on_brace=True, use_escaping=use_escaping)
        if cur.peek() != "}":
            raise L10nError(f"unclosed ICU selector body for {selector!r}")
        cur.i += 1
        options.append((selector, tuple(body)))
        _skip_ws(cur)
    if not options:
        raise L10nError("ICU plural/select has no selectors")
    return options


def _parse_selector(cur: _Cursor) -> str:
    if cur.peek() == "=":
        start = cur.i
        cur.i += 1
        if not cur.peek().isdigit() and cur.peek() != "-":
            raise L10nError("ICU '=' selector is missing a number")
        if cur.peek() == "-":
            cur.i += 1
        while cur.peek().isdigit():
            cur.i += 1
        return cur.text[start : cur.i]
    ident = _parse_ident(cur)
    return ident


def _parse_ident(cur: _Cursor) -> str:
    match = IDENT_RE.match(cur.remaining())
    if not match:
        raise L10nError(f"expected identifier in ICU message at index {cur.i}")
    cur.i += match.end()
    return match.group(0)


def _skip_ws(cur: _Cursor) -> None:
    while cur.peek().isspace():
        cur.i += 1


def icu_structure(message: str, use_escaping: bool = False) -> tuple[Any, ...]:
    try:
        return tuple(parse_icu(message, use_escaping=use_escaping))
    except L10nError:
        # Fall back to placeholder names so a parse failure still refuses a mismatch.
        return tuple(("ph", name) for name in placeholder_names_fallback(message, use_escaping=use_escaping))


def placeholder_names_fallback(message: str, use_escaping: bool = False) -> list[str]:
    names: list[str] = []
    cur = _Cursor(message)
    while not cur.eof():
        ch = cur.peek()
        if ch == "'" and use_escaping:
            _skip_quoted(cur)
            continue
        if ch == "{":
            cur.i += 1
            match = IDENT_RE.match(cur.remaining())
            if match:
                names.append(match.group(0))
                cur.i += match.end()
            continue
        cur.i += 1
    return names


def placeholder_names(message: str, use_escaping: bool = False) -> set[str]:
    names: set[str] = set()

    def walk(nodes: list[Any] | tuple[Any, ...]) -> None:
        for node in nodes:
            if not isinstance(node, tuple) or not node:
                continue
            kind = node[0]
            if kind in {"ph", "typed", "plural", "select"}:
                names.add(node[1])
            if kind in {"plural", "select"}:
                for _selector, body in node[2]:
                    walk(body)

    try:
        walk(parse_icu(message, use_escaping=use_escaping))
    except L10nError:
        names.update(placeholder_names_fallback(message, use_escaping=use_escaping))
    return names


def require_same_icu(english: str, translated: str, locale: str, key: str, use_escaping: bool = False) -> None:
    if icu_structure(english, use_escaping=use_escaping) != icu_structure(translated, use_escaping=use_escaping):
        raise L10nError(
            f"locale {locale}: {key!r} ICU placeholders/plural/select structure does not match English\n"
            f"  en: {english}\n"
            f"  {locale}: {translated}"
        )


def require_placeholder_subset(
    english: str, translated: str, locale: str, key: str, use_escaping: bool = False
) -> None:
    en_names = placeholder_names(english, use_escaping=use_escaping)
    tr_names = placeholder_names(translated, use_escaping=use_escaping)
    unknown = tr_names - en_names
    if unknown:
        raise L10nError(
            f"locale {locale}: {key!r} uses placeholders {sorted(unknown)} that English does not declare"
        )


# --- ARB mutation ----------------------------------------------------------


def parse_placeholders_flag(raw: str | None, english: str, use_escaping: bool = False) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise L10nError(f"--placeholders is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise L10nError("--placeholders must be a non-empty JSON object")
    if any(not isinstance(k, str) or not isinstance(v, dict) for k, v in data.items()):
        raise L10nError("--placeholders values must be JSON objects keyed by placeholder name")
    declared = set(data)
    used = placeholder_names(english, use_escaping=use_escaping)
    missing = used - declared
    extra = declared - used
    if missing or extra:
        raise L10nError(
            f"--placeholders must match ICU names in English (missing {sorted(missing) or '-'}, "
            f"unknown {sorted(extra) or '-'})"
        )
    return data


def metadata_for(description: str | None, placeholders: dict[str, Any] | None) -> dict[str, Any] | None:
    meta: dict[str, Any] = {}
    if description:
        meta["description"] = description
    if placeholders:
        meta["placeholders"] = placeholders
    return meta or None


def load_translations_file(
    path: Path,
    locales: set[str],
    english: str | None,
) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L10nError(f"translations file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise L10nError("translations file must be a JSON object mapping locale → string")
    for locale, value in data.items():
        if not isinstance(locale, str) or not isinstance(value, str):
            raise L10nError("translations file values must be strings keyed by locale code")
        if value == "":
            raise L10nError(f"locale {locale}: translation is empty (fill the template before add/set)")
    unknown = set(data) - locales
    if unknown:
        raise L10nError(f"translations file has unknown locales: {', '.join(sorted(unknown))}")
    required = set(locales)
    if english is not None:
        required -= {"en"}
    missing = required - set(data)
    if missing:
        raise L10nError(
            f"translations file is missing locales: {', '.join(sorted(missing))}\n"
            f"Run: python3 scripts/l10n.py template <key>"
        )
    if "en" in data and english is not None and data["en"] != english:
        raise L10nError("translations file en value does not match --en")
    result = {locale: data[locale] for locale in locales if locale in data}
    if english is not None:
        result["en"] = english
    return result


def values_and_meta_identical(
    loaded: dict[str, dict[str, Any]],
    key: str,
    translations: dict[str, str],
    meta: dict[str, Any] | None,
) -> bool:
    for locale, data in loaded.items():
        if data.get(key) != translations[locale]:
            return False
    en = loaded["en"]
    existing_meta = en.get(f"@{key}")
    if meta is None:
        return existing_meta is None or existing_meta == {}
    return existing_meta == meta


def apply_add(
    loaded: dict[str, dict[str, Any]],
    key: str,
    translations: dict[str, str],
    meta: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    present = [locale for locale, data in loaded.items() if key in data]
    if present:
        if len(present) == len(loaded) and values_and_meta_identical(loaded, key, translations, meta):
            return loaded
        if len(present) == len(loaded):
            raise L10nError(f"key {key!r} already exists (values differ; use set to change it)")
        raise L10nError(
            f"key {key!r} already exists in {', '.join(sorted(present))} but not every locale; use set to repair"
        )
    out: dict[str, dict[str, Any]] = {}
    for locale, data in loaded.items():
        new = dict(data)
        new[key] = translations[locale]
        if locale == "en" and meta is not None:
            new[f"@{key}"] = meta
        out[locale] = new
    return out


def apply_set(
    loaded: dict[str, dict[str, Any]],
    key: str,
    translations: dict[str, str],
    meta: dict[str, Any] | None,
    update_meta: bool,
) -> dict[str, dict[str, Any]]:
    if key not in loaded["en"]:
        raise L10nError(f"key {key!r} does not exist (use add)")
    out: dict[str, dict[str, Any]] = {}
    for locale, data in loaded.items():
        new = dict(data)
        new[key] = translations[locale]
        if locale == "en" and update_meta:
            if meta is None:
                new.pop(f"@{key}", None)
            else:
                existing = dict(new.get(f"@{key}") or {})
                existing.update(meta)
                new[f"@{key}"] = existing
        out[locale] = new
    return out


def apply_remove(loaded: dict[str, dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for locale, data in loaded.items():
        new = dict(data)
        new.pop(key, None)
        new.pop(f"@{key}", None)
        out[locale] = new
    return out


def planned_texts(by_locale: dict[str, Path], updated: dict[str, dict[str, Any]]) -> dict[Path, str]:
    planned: dict[Path, str] = {}
    for locale, data in updated.items():
        path = by_locale[locale]
        new_text = dump_arb(data)
        if path.read_text(encoding="utf-8") != new_text:
            planned[path] = new_text
    return planned


def write_atomic(planned: dict[Path, str]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for path, text in planned.items():
            tmp = path.with_name(path.name + ".l10n-tmp")
            tmp.write_text(text, encoding="utf-8")
            staged.append((path, tmp))
        for path, tmp in staged:
            os.replace(tmp, path)
            staged = [(p, t) for p, t in staged if p != path]
    except Exception:
        for _path, tmp in staged:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def restore_texts(originals: dict[Path, str]) -> None:
    for path, text in originals.items():
        path.write_text(text, encoding="utf-8")


def validate_new_values(translations: dict[str, str], key: str, use_escaping: bool = False) -> None:
    english = translations["en"]
    for locale, value in translations.items():
        if locale == "en":
            continue
        require_same_icu(english, value, locale, key, use_escaping=use_escaping)


# --- codegen ---------------------------------------------------------------


def is_flutter_app(app_dir: Path) -> bool:
    return (app_dir / "pubspec.yaml").is_file() and (app_dir / "l10n.yaml").is_file()


def require_package_config(app_dir: Path) -> None:
    if not (app_dir / ".dart_tool" / "package_config.json").is_file():
        raise L10nError(f"{app_dir}: run `flutter pub get` so gen-l10n formats with page_width 120")


def _flutter() -> str:
    path = shutil.which("flutter")
    if not path:
        raise L10nError("flutter is not on PATH")
    return path


def _dart() -> str:
    path = shutil.which("dart")
    if path:
        return path
    flutter = shutil.which("flutter")
    if flutter:
        sibling = Path(flutter).resolve().parent / "dart"
        if sibling.is_file():
            return str(sibling)
    raise L10nError("dart is not on PATH")


def run_gen_l10n(app_dir: Path, untranslated_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    yaml_path = app_dir / "l10n.yaml"
    original = yaml_path.read_text(encoding="utf-8")
    patched = original
    if untranslated_path is not None and "untranslated-messages-file:" not in original:
        patched = original.rstrip() + f"\nuntranslated-messages-file: {untranslated_path}\n"
        yaml_path.write_text(patched, encoding="utf-8")
    try:
        return subprocess.run(
            [_flutter(), "gen-l10n"],
            cwd=app_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        if patched != original:
            yaml_path.write_text(original, encoding="utf-8")


def run_dart_format(app_dir: Path, files: list[Path]) -> None:
    if not files:
        return
    result = subprocess.run(
        [_dart(), "format", "--line-length", "120", *[str(p) for p in files]],
        cwd=app_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise L10nError(f"dart format failed:\n{result.stderr or result.stdout}")


def generated_dart_files(arb_dir: Path) -> list[Path]:
    return sorted(p for p in arb_dir.glob("app_localizations*.dart") if p.is_file())


def parse_untranslated_file(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for locale, keys in data.items():
        if isinstance(keys, list):
            out[str(locale)] = [str(k) for k in keys]
    return out


def assert_key_translated(untranslated: dict[str, list[str]], key: str) -> None:
    offenders = sorted(locale for locale, keys in untranslated.items() if key in keys)
    if offenders:
        raise L10nError(f"key {key!r} is still untranslated in: {', '.join(offenders)}")


def codegen(app_dir: Path, arb_dir: Path, expect_key: str | None) -> None:
    require_package_config(app_dir)
    with tempfile.TemporaryDirectory(prefix="omi-l10n-") as tmp:
        untranslated_path = Path(tmp) / "untranslated.json"
        result = run_gen_l10n(app_dir, untranslated_path)
        combined = (result.stdout or "") + (result.stderr or "")
        sys.stderr.write(result.stderr)
        if result.returncode != 0:
            raise L10nError(f"flutter gen-l10n failed:\n{combined}")
        untranslated = parse_untranslated_file(untranslated_path)
        if expect_key:
            assert_key_translated(untranslated, expect_key)
        leftover = {locale: keys for locale, keys in untranslated.items() if keys}
        if leftover and expect_key:
            sample = sorted({k for keys in leftover.values() for k in keys})
            print(
                f"note: {len(sample)} pre-existing untranslated key(s) remain "
                f"({', '.join(sample[:8])}{'…' if len(sample) > 8 else ''}); {expect_key!r} is complete.",
                file=sys.stderr,
            )
        elif leftover:
            raise L10nError(
                "untranslated messages remain:\n"
                + "\n".join(f"  {locale}: {', '.join(keys)}" for locale, keys in sorted(leftover.items()))
            )
    run_dart_format(app_dir, generated_dart_files(arb_dir))


def codegen_freshness(app_dir: Path, arb_dir: Path) -> None:
    """Re-run gen-l10n in place and restore. Alternate output-dir paths rewrite the
    import comment in app_localizations.dart, so a temp dir is not a valid compare.
    """
    require_package_config(app_dir)
    before = generated_dart_files(arb_dir)
    originals = {path: path.read_text(encoding="utf-8") for path in before}
    before_names = {p.name for p in before}
    try:
        result = subprocess.run(
            [_flutter(), "gen-l10n"],
            cwd=app_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise L10nError(f"flutter gen-l10n failed during check:\n{result.stderr or result.stdout}")
        after = generated_dart_files(arb_dir)
        run_dart_format(app_dir, after)
        after = generated_dart_files(arb_dir)
        after_names = {p.name for p in after}
        missing = after_names - before_names
        extra = before_names - after_names
        if missing or extra:
            raise L10nError(
                "generated Dart set does not match gen-l10n output "
                f"(missing {sorted(missing) or '-'}, extra {sorted(extra) or '-'})"
            )
        diffs = [
            path.name
            for path in after
            if originals[path] != path.read_text(encoding="utf-8")
        ]
        if diffs:
            raise L10nError(
                "generated localization Dart is stale; run from app/: "
                f"flutter gen-l10n && dart format --line-length 120 lib/l10n/app_localizations*.dart\n"
                f"  drifted: {', '.join(diffs[:12])}{'…' if len(diffs) > 12 else ''}"
            )
    finally:
        restore_texts(originals)
        for path in generated_dart_files(arb_dir):
            if path not in originals:
                try:
                    path.unlink()
                except OSError:
                    pass


# --- commands --------------------------------------------------------------


_USE_ESCAPING_TRUE = {"true", "yes", "1", "on"}


def read_use_escaping(app_dir: Path) -> bool:
    """Match Flutter gen-l10n: ICU apostrophe quoting applies only if use-escaping is true.

    Missing l10n.yaml or missing key → False (Flutter default, and this repo's
    ``app/l10n.yaml``).
    """
    path = app_dir / "l10n.yaml"
    if not path.is_file():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line.startswith("use-escaping"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip() != "use-escaping":
            continue
        return value.strip().strip("'\"").lower() in _USE_ESCAPING_TRUE
    return False


def resolve_dirs(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.arb_dir:
        arb_dir = Path(args.arb_dir).resolve()
    else:
        arb_dir = Path(__file__).resolve().parent.parent / "lib" / "l10n"
    if args.app_dir:
        app_dir = Path(args.app_dir).resolve()
    elif arb_dir.name == "l10n" and arb_dir.parent.name == "lib":
        app_dir = arb_dir.parent.parent
    else:
        app_dir = arb_dir
    if not arb_dir.is_dir():
        raise L10nError(f"ARB directory does not exist: {arb_dir}")
    return arb_dir, app_dir


def validate_key(key: str) -> None:
    if not KEY_RE.fullmatch(key):
        raise L10nError(f"key {key!r} must be a Dart camelCase identifier (e.g. failedToShareRecap)")


def mutate_and_write(
    by_locale: dict[str, Path],
    updated: dict[str, dict[str, Any]],
    app_dir: Path,
    arb_dir: Path,
    expect_key: str | None,
    do_codegen: bool,
) -> str:
    planned = planned_texts(by_locale, updated)
    if not planned:
        return "noop"
    originals = {path: path.read_text(encoding="utf-8") for path in planned}
    generated = generated_dart_files(arb_dir) if do_codegen else []
    generated_originals = {path: path.read_text(encoding="utf-8") for path in generated}
    write_atomic(planned)
    if not do_codegen:
        return "wrote"
    try:
        codegen(app_dir, arb_dir, expect_key)
    except Exception:
        restore_texts(originals)
        restore_texts(generated_originals)
        raise
    return "wrote"


def cmd_template(args: argparse.Namespace) -> int:
    arb_dir, _app_dir = resolve_dirs(args)
    by_locale = discover_arb_files(arb_dir)
    skeleton = {locale: "" for locale in sorted(by_locale)}
    json.dump(skeleton, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    if args.key:
        print(f"Fill every locale for {args.key!r}, then: l10n add {args.key} --en \"...\" --translations <file>", file=sys.stderr)
    else:
        print(f"{len(by_locale)} locales. Fill every value; empty strings are refused.", file=sys.stderr)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    validate_key(args.key)
    arb_dir, app_dir = resolve_dirs(args)
    by_locale = discover_arb_files(arb_dir)
    loaded = load_all_arbs(by_locale)
    use_escaping = read_use_escaping(app_dir)
    placeholders = parse_placeholders_flag(args.placeholders, args.en, use_escaping=use_escaping)
    meta = metadata_for(args.description, placeholders)
    translations = load_translations_file(Path(args.translations), set(by_locale), args.en)
    validate_new_values(translations, args.key, use_escaping=use_escaping)
    updated = apply_add(loaded, args.key, translations, meta)
    do_codegen = is_flutter_app(app_dir)
    status = mutate_and_write(by_locale, updated, app_dir, arb_dir, args.key, do_codegen)
    if status == "noop":
        print(f"already up to date: {args.key}")
    else:
        print(f"added {args.key} to {len(by_locale)} locales" + ("" if do_codegen else " (ARB only; no Flutter app at --app-dir)"))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    validate_key(args.key)
    arb_dir, app_dir = resolve_dirs(args)
    by_locale = discover_arb_files(arb_dir)
    loaded = load_all_arbs(by_locale)
    if args.key not in loaded["en"]:
        raise L10nError(f"key {args.key!r} does not exist (use add)")
    english = args.en if args.en is not None else loaded["en"][args.key]
    if not isinstance(english, str):
        raise L10nError(f"key {args.key!r} English value is not a string")
    if args.translations:
        translations = load_translations_file(Path(args.translations), set(by_locale), english)
    else:
        translations = {locale: data[args.key] for locale, data in loaded.items() if args.key in data}
        if set(translations) != set(by_locale):
            raise L10nError(
                f"key {args.key!r} is missing from some locales; pass --translations covering every locale"
            )
        translations["en"] = english
    update_meta = args.description is not None or args.placeholders is not None
    use_escaping = read_use_escaping(app_dir)
    placeholders = (
        parse_placeholders_flag(args.placeholders, english, use_escaping=use_escaping)
        if args.placeholders is not None
        else None
    )
    if args.placeholders is None and update_meta:
        existing = loaded["en"].get(f"@{args.key}")
        if isinstance(existing, dict) and isinstance(existing.get("placeholders"), dict):
            placeholders = existing["placeholders"]
    description = args.description
    if description is None and update_meta:
        existing = loaded["en"].get(f"@{args.key}")
        if isinstance(existing, dict) and isinstance(existing.get("description"), str):
            description = existing["description"]
    meta = metadata_for(description, placeholders) if update_meta else None
    validate_new_values(translations, args.key, use_escaping=use_escaping)
    updated = apply_set(loaded, args.key, translations, meta, update_meta)
    if not update_meta and values_and_meta_identical(loaded, args.key, translations, loaded["en"].get(f"@{args.key}") if isinstance(loaded["en"].get(f"@{args.key}"), dict) else None):
        print(f"already up to date: {args.key}")
        return 0
    do_codegen = is_flutter_app(app_dir)
    status = mutate_and_write(by_locale, updated, app_dir, arb_dir, args.key, do_codegen)
    if status == "noop":
        print(f"already up to date: {args.key}")
    else:
        print(f"updated {args.key} in {len(by_locale)} locales")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    validate_key(args.key)
    arb_dir, app_dir = resolve_dirs(args)
    by_locale = discover_arb_files(arb_dir)
    loaded = load_all_arbs(by_locale)
    present = any(args.key in data for data in loaded.values())
    if not present:
        print(f"already absent: {args.key}")
        return 0
    updated = apply_remove(loaded, args.key)
    do_codegen = is_flutter_app(app_dir)
    status = mutate_and_write(by_locale, updated, app_dir, arb_dir, None, do_codegen)
    if status == "noop":
        print(f"already absent: {args.key}")
    else:
        print(f"removed {args.key} from {len(by_locale)} locales")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    arb_dir, app_dir = resolve_dirs(args)
    by_locale = discover_arb_files(arb_dir)
    loaded = load_all_arbs(by_locale)
    template_keys = message_keys(loaded["en"])
    use_escaping = read_use_escaping(app_dir)
    errors: list[str] = []
    for locale, data in sorted(loaded.items()):
        keys = message_keys(data)
        missing = template_keys - keys
        extra = keys - template_keys
        if missing:
            errors.append(f"{locale}: missing {', '.join(sorted(missing)[:12])}{'…' if len(missing) > 12 else ''}")
        if extra:
            errors.append(f"{locale}: extra {', '.join(sorted(extra)[:12])}{'…' if len(extra) > 12 else ''}")
    for key in sorted(template_keys):
        english = loaded["en"].get(key)
        if not isinstance(english, str):
            continue
        for locale, data in loaded.items():
            if locale == "en":
                continue
            value = data.get(key)
            if not isinstance(value, str):
                continue
            try:
                require_placeholder_subset(english, value, locale, key, use_escaping=use_escaping)
            except L10nError as exc:
                errors.append(str(exc))
    if errors:
        raise L10nError("l10n check failed:\n" + "\n".join(f"  {e}" for e in errors))
    if is_flutter_app(app_dir) and (app_dir / ".dart_tool" / "package_config.json").is_file():
        codegen_freshness(app_dir, arb_dir)
    print(f"ok: {len(by_locale)} locales, {len(template_keys)} keys")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="l10n",
        description="Add, change, or remove a localized string across every ARB locale.",
    )
    parser.add_argument("--arb-dir", help="Directory of app_*.arb files (default: app/lib/l10n)")
    parser.add_argument("--app-dir", help="Flutter app root containing l10n.yaml (default: inferred)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Insert a new key into every locale")
    p_add.add_argument("key")
    p_add.add_argument("--en", required=True, help="English source string")
    p_add.add_argument("--description", help="Translator description (written on @key in app_en.arb)")
    p_add.add_argument("--placeholders", help="ARB placeholders JSON object")
    p_add.add_argument("--translations", required=True, help="JSON file mapping locale → string")
    p_add.set_defaults(func=cmd_add)

    p_set = sub.add_parser("set", help="Change an existing key")
    p_set.add_argument("key")
    p_set.add_argument("--en", help="New English source string")
    p_set.add_argument("--description")
    p_set.add_argument("--placeholders")
    p_set.add_argument("--translations", help="JSON file mapping locale → string (required unless only metadata changes)")
    p_set.set_defaults(func=cmd_set)

    p_remove = sub.add_parser("remove", help="Delete a key from every locale")
    p_remove.add_argument("key")
    p_remove.set_defaults(func=cmd_remove)

    p_template = sub.add_parser("template", help="Print a translations JSON skeleton for every locale")
    p_template.add_argument("key", nargs="?", default="")
    p_template.set_defaults(func=cmd_template)

    p_check = sub.add_parser("check", help="Parse ARBs, compare key sets and placeholders, verify generated Dart")
    p_check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except L10nError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
