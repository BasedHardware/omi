"""Rebuild docs/PARITY.md from evidence: one row per iOS Swift file with views.

A row is ✅ when every view has a Kotlin function of the same name (or lowerCamel), every catalog
key the Swift file uses is used somewhere in Android, and the Kotlin files holding those views carry
no TODO(visual-stub). Otherwise 🟡 with what is missing, ❌ when no view was found at all.
Usage: parity_table.py <omi-native> <omi-android> <ios-sha> <android-sha> <parity_config.json>
"""
import collections
import json
import pathlib
import re
import sys

ios, android = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
ios_sha, android_sha = sys.argv[3], sys.argv[4]
config = json.loads(pathlib.Path(sys.argv[5]).read_text())
# Files that are iOS only by nature: {swift file: note}.
platform = config["platform_files"]
# Views and keys checked by hand: {Swift view: Kotlin function}, {iOS key: Android key}, and parts of a
# file that are iOS only ({swift file: [view or key, ...]}).
view_aliases, key_aliases, ios_only = config["view_aliases"], config["key_aliases"], config["ios_only"]

catalog = set(re.findall(r'<string name="([^"]+)"', (android / "design/src/main/res/values/strings.xml").read_text()))
literal = re.compile(r'"([A-Za-z][A-Za-z0-9_]{2,})"')
view = re.compile(r"^\s*(?:public |private |fileprivate |internal )?struct\s+(\w+)\s*(?:<[^>]*>)?\s*:\s*[^{]*\bView\b", re.M)
kt_fun = re.compile(r"\bfun\s+(?:<[^>]*>\s*)?(?:[\w.<>]+\.)?(\w+)\s*\(")

kotlin_defs = collections.defaultdict(set)  # name -> files
android_keys = set()
stub_files = set()
for f in android.rglob("*.kt"):
    s = str(f)
    if "/build/" in s or "/test/" in s:
        continue
    text = f.read_text(errors="ignore")
    rel = str(f.relative_to(android))
    for name in kt_fun.findall(text):
        kotlin_defs[name].add(rel)
    android_keys.update(k for k in literal.findall(text) if k in catalog)
    if "TODO(visual-stub)" in text:
        stub_files.add(rel)


def short(path: str) -> str:
    return re.sub(r"^(features|service|network|design|app|core|audio|device)/src/main/kotlin/com/friend/ios/", r"\1/.../", path)


rows = []
for f in sorted(list((ios / "App").rglob("*.swift")) + list((ios / "Packages/OmiFeatures/Sources").rglob("*.swift"))):
    rel = str(f.relative_to(ios))
    if "/.build/" in rel:
        continue
    text = f.read_text(errors="ignore")
    views = view.findall(text)
    if not views:
        continue
    loc = text.count("\n")
    files, missing_views = set(), []
    for v in views:
        if v in ios_only.get(rel, []):
            continue
        alias = view_aliases.get(v)
        hits = kotlin_defs.get(v) or kotlin_defs.get(v[0].lower() + v[1:]) or (kotlin_defs.get(alias) if alias else None)
        if hits:
            files.update(hits)
        else:
            missing_views.append(v)
    keys = {k for k in literal.findall(text) if k in catalog}
    keys = {k for k in keys if k not in ios_only.get(rel, []) and key_aliases.get(k) not in android_keys}
    missing_keys = sorted(keys - android_keys)
    stubs = sorted(short(p) for p in files if p in stub_files)
    kotlin = ", ".join(f"`{short(p)}`" for p in sorted(files)) or "none"
    if rel in platform:
        status = f"➖ iOS only: {platform[rel]}"
    elif not files:
        status = "❌ no Kotlin view"
    elif missing_views or missing_keys or stubs:
        parts = []
        if missing_views:
            parts.append("views " + ", ".join(missing_views))
        if missing_keys:
            parts.append("text " + ", ".join(missing_keys))
        if stubs:
            parts.append("stub in " + ", ".join(stubs))
        status = "🟡 " + "; ".join(parts)
    else:
        status = "✅"
    rows.append((rel, loc, ", ".join(views), kotlin, status))

count = collections.Counter(r[4][0] for r in rows)
print("# Parity: omi-native iOS -> Android\n")
print("One row per Swift file with views (features + app shell), rebuilt from the code by")
print("`Tools/parity/parity_table.py`: ✅ every view has its Kotlin composable, every text key the file uses")
print("is used on Android and those Kotlin files carry no `TODO(visual-stub)`; 🟡 says what is missing;")
print("➖ is iOS only by nature; ❌ has no Kotlin view.")
print(f"Built from omi-native `{ios_sha}` and omi-android `{android_sha}`: {len(rows)} rows, "
      f"{count['✅']} ✅, {count['🟡']} 🟡, {count['➖']} ➖, {count['❌']} ❌.\n")
print("| Swift file | LOC | Views | Kotlin | Status |")
print("|---|---|---|---|---|")
for rel, loc, views, kotlin, status in rows:
    print(f"| `{rel}` | {loc} | {views} | {kotlin} | {status} |")
