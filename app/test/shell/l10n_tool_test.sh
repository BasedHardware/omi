#!/usr/bin/env bash
#
# Contract tests for app/scripts/l10n.py: refusal cases, ICU mismatch,
# identical re-run no-op, and a byte-exact add against copies of two real ARB files.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
L10N="$APP_DIR/scripts/l10n.py"
EN_ARB="$APP_DIR/lib/l10n/app_en.arb"
FR_ARB="$APP_DIR/lib/l10n/app_fr.arb"

failures=0
pass() { echo "  ok   - $1"; }
fail() { echo "  FAIL - $1" >&2; failures=$((failures + 1)); }

[[ -f "$L10N" ]] || { echo "FAIL: missing $L10N" >&2; exit 1; }
[[ -f "$EN_ARB" && -f "$FR_ARB" ]] || { echo "FAIL: missing real ARB fixtures" >&2; exit 1; }

work="$(mktemp -d "${TMPDIR:-/tmp}/omi-l10n-tool.XXXXXX")"
trap 'rm -rf "$work"' EXIT

mini="$work/mini"
mkdir -p "$mini"

python3 - "$mini" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
en = {
    "@@locale": "en",
    "hello": "Hello {name}",
    "@hello": {
        "description": "Greeting",
        "placeholders": {"name": {"type": "String"}},
    },
}
fr = {"@@locale": "fr", "hello": "Bonjour {name}"}
de = {"@@locale": "de", "hello": "Hallo {name}"}
for loc, data in (("en", en), ("fr", fr), ("de", de)):
    (root / f"app_{loc}.arb").write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
PY

run_l10n() {
  python3 "$L10N" --arb-dir "$mini" "$@"
}

echo "l10n tool (mini fixture):"

template_out="$work/template.json"
if python3 "$L10N" --arb-dir "$mini" template greet >"$template_out" 2>"$work/template.err"; then
  python3 - "$template_out" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert set(data) == {"de", "en", "fr"}, data
assert all(v == "" for v in data.values()), data
PY
  pass "template lists every locale in the arb dir"
else
  fail "template exited non-zero"
fi

# Existing key, different value — refuse, no writes.
cp "$mini/app_en.arb" "$work/en.before"
printf '%s\n' '{"de":"Hallo","en":"Hello","fr":"Bonjour"}' >"$work/tr-existing.json"
if run_l10n add hello --en "Hello" --translations "$work/tr-existing.json" 2>"$work/exists.err"; then
  fail "add accepted a key that already exists with different values"
else
  grep -q "already exists" "$work/exists.err" || fail "add existing-key error did not mention already exists"
  cmp -s "$mini/app_en.arb" "$work/en.before" && pass "add refuses an existing different key without writing" || fail "add mutated ARBs after existing-key refusal"
fi

# Missing locale.
printf '%s\n' '{"fr":"Salut tout le monde"}' >"$work/tr-missing.json"
if run_l10n add brandNew --en "Hello everyone" --translations "$work/tr-missing.json" 2>"$work/missing.err"; then
  fail "add accepted a translations file missing locales"
else
  grep -q "missing locales" "$work/missing.err" && pass "add refuses a translations file missing a locale" || fail "missing-locale error text"
  cmp -s "$mini/app_en.arb" "$work/en.before" && pass "add missing-locale is atomic (no writes)" || fail "add wrote files after missing-locale refusal"
fi

# Unknown locale.
printf '%s\n' '{"de":"Hallo zusammen","fr":"Salut tout le monde","xx":"nope"}' >"$work/tr-unknown.json"
if run_l10n add brandNew --en "Hello everyone" --translations "$work/tr-unknown.json" 2>"$work/unknown.err"; then
  fail "add accepted an unknown locale"
else
  grep -q "unknown locales" "$work/unknown.err" && pass "add refuses unknown locales" || fail "unknown-locale error text"
  cmp -s "$mini/app_en.arb" "$work/en.before" || fail "add wrote files after unknown-locale refusal"
fi

# Placeholder mismatch.
printf '%s\n' '{"de":"Hallo","fr":"Salut"}' >"$work/tr-ph.json"
if run_l10n add withName --en "Hello {name}" --translations "$work/tr-ph.json" 2>"$work/ph.err"; then
  fail "add accepted a placeholder mismatch"
else
  grep -q "ICU placeholders" "$work/ph.err" && pass "add refuses a placeholder/plural mismatch" || fail "placeholder mismatch error text"
  cmp -s "$mini/app_en.arb" "$work/en.before" || fail "add wrote files after placeholder refusal"
fi

# Plural structure mismatch.
printf '%s\n' '{"de":"{count} Dateien","fr":"{count} fichiers"}' >"$work/tr-plural.json"
if run_l10n add fileCount --en "{count, plural, =1{1 file} other{{count} files}}" --translations "$work/tr-plural.json" 2>"$work/plural.err"; then
  fail "add accepted a flattened plural that does not match English"
else
  grep -q "ICU placeholders" "$work/plural.err" && pass "add refuses a flattened plural vs English plural" || fail "plural mismatch error text"
fi

# Happy add.
printf '%s\n' '{"de":"Hallo alle","en":"Hello everyone","fr":"Salut tout le monde"}' >"$work/tr-ok.json"
if run_l10n add helloEveryone --en "Hello everyone" --description "Generic greeting" --translations "$work/tr-ok.json" >"$work/add.out" 2>"$work/add.err"; then
  python3 - "$mini" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
en = json.loads((root / "app_en.arb").read_text())
fr = json.loads((root / "app_fr.arb").read_text())
de = json.loads((root / "app_de.arb").read_text())
assert en["helloEveryone"] == "Hello everyone"
assert en["@helloEveryone"]["description"] == "Generic greeting"
assert fr["helloEveryone"] == "Salut tout le monde"
assert de["helloEveryone"] == "Hallo alle"
assert "@helloEveryone" not in fr
PY
  pass "add writes the key, English @key metadata, and every translation"
else
  fail "add of a new key failed: $(cat "$work/add.err")"
fi

cp "$mini/app_en.arb" "$work/en.after-add"
cp "$mini/app_fr.arb" "$work/fr.after-add"
cp "$mini/app_de.arb" "$work/de.after-add"
if run_l10n add helloEveryone --en "Hello everyone" --description "Generic greeting" --translations "$work/tr-ok.json" >"$work/noop.out" 2>"$work/noop.err"; then
  grep -q "already up to date" "$work/noop.out" || fail "identical re-run did not report already up to date"
  cmp -s "$mini/app_en.arb" "$work/en.after-add" && cmp -s "$mini/app_fr.arb" "$work/fr.after-add" && cmp -s "$mini/app_de.arb" "$work/de.after-add" \
    && pass "identical add re-run is a byte-level no-op" \
    || fail "identical add re-run mutated ARB bytes"
else
  fail "identical add re-run exited non-zero"
fi

if run_l10n check >"$work/check.out" 2>"$work/check.err"; then
  grep -q "3 locales" "$work/check.out" && pass "check passes a consistent mini fixture" || fail "check output missing locale count"
else
  fail "check failed on a consistent fixture: $(cat "$work/check.err")"
fi

# check: missing key
python3 - "$mini" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / "app_fr.arb"
data = json.loads(path.read_text())
del data["helloEveryone"]
path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
PY
if run_l10n check >"$work/check-miss.out" 2>"$work/check-miss.err"; then
  fail "check accepted a missing key in one locale"
else
  grep -q "missing" "$work/check-miss.err" && pass "check fails when a locale is missing a key" || fail "check missing-key error text"
fi
cp "$work/fr.after-add" "$mini/app_fr.arb"

# remove + idempotent remove
if run_l10n remove helloEveryone >"$work/rm.out" 2>"$work/rm.err"; then
  python3 - "$mini" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
for name in ("app_en.arb", "app_fr.arb", "app_de.arb"):
    data = json.loads((root / name).read_text())
    assert "helloEveryone" not in data
    assert "@helloEveryone" not in data
PY
  pass "remove deletes the key and English metadata from every locale"
else
  fail "remove failed: $(cat "$work/rm.err")"
fi
if run_l10n remove helloEveryone >"$work/rm2.out" 2>"$work/rm2.err"; then
  grep -q "already absent" "$work/rm2.out" && pass "remove of an absent key is a no-op" || fail "absent remove message"
else
  fail "absent remove exited non-zero"
fi

echo
echo "l10n tool (byte-exact add on copies of two real ARB files):"

real="$work/real"
mkdir -p "$real"
cp "$EN_ARB" "$real/app_en.arb"
cp "$FR_ARB" "$real/app_fr.arb"
cp "$real/app_en.arb" "$work/real-en.before"
cp "$real/app_fr.arb" "$work/real-fr.before"

printf '%s\n' '{"en":"Byte-exact probe string","fr":"Chaîne de sonde exacte"}' >"$work/tr-real.json"
if python3 "$L10N" --arb-dir "$real" add byteExactProbe --en "Byte-exact probe string" --description "Shell-test probe; not shipped" --translations "$work/tr-real.json" >"$work/real-add.out" 2>"$work/real-add.err"; then
  python3 - "$work/real-en.before" "$real/app_en.arb" "$work/real-fr.before" "$real/app_fr.arb" <<'PY'
import json, sys
from pathlib import Path

def dump(data):
    return json.dumps(data, indent=4, ensure_ascii=False) + "\n"

en_before = Path(sys.argv[1]).read_text(encoding="utf-8")
en_after = Path(sys.argv[2]).read_text(encoding="utf-8")
fr_before = Path(sys.argv[3]).read_text(encoding="utf-8")
fr_after = Path(sys.argv[4]).read_text(encoding="utf-8")
assert dump(json.loads(en_before)) == en_before, "copied English ARB is not dump-identity"
assert dump(json.loads(fr_before)) == fr_before, "copied French ARB is not dump-identity"

en_old = json.loads(en_before)
en_new = json.loads(en_after)
fr_old = json.loads(fr_before)
fr_new = json.loads(fr_after)
assert set(en_new) - set(en_old) == {"byteExactProbe", "@byteExactProbe"}
assert set(fr_new) - set(fr_old) == {"byteExactProbe"}
for k, v in en_old.items():
    assert en_new[k] == v
for k, v in fr_old.items():
    assert fr_new[k] == v
assert en_new["byteExactProbe"] == "Byte-exact probe string"
assert en_new["@byteExactProbe"]["description"] == "Shell-test probe; not shipped"
assert fr_new["byteExactProbe"] == "Chaîne de sonde exacte"

# Only the previous last entry gains a comma, then the new key (and @key) lines.
def only_appended(before: str, after: str, extra_keys: list[str]) -> None:
    old = json.loads(before)
    expected = dict(old)
    # Rebuild the expected file the same way the tool does: keep order, append keys.
    # extra_keys already present in `after`; compare dumps.
    new = json.loads(after)
    assert dump(new) == after
    assert before.endswith("}\n")
    # Character-level: after must equal dump(old-with-appended-keys)
    rebuilt = dict(old)
    for k in extra_keys:
        rebuilt[k] = new[k]
    assert dump(rebuilt) == after, "add rewrote more than the appended keys"

only_appended(en_before, en_after, ["byteExactProbe", "@byteExactProbe"])
only_appended(fr_before, fr_after, ["byteExactProbe"])
PY
  pass "add against copies of app_en.arb and app_fr.arb appends only the new key"
else
  fail "real-ARB add failed: $(cat "$work/real-add.err")"
fi

cp "$real/app_en.arb" "$work/real-en.after-add"
cp "$real/app_fr.arb" "$work/real-fr.after-add"
if python3 "$L10N" --arb-dir "$real" add byteExactProbe --en "Byte-exact probe string" --description "Shell-test probe; not shipped" --translations "$work/tr-real.json" >"$work/real-noop.out" 2>"$work/real-noop.err"; then
  grep -q "already up to date" "$work/real-noop.out" || fail "real identical re-run did not report already up to date"
  cmp -s "$real/app_en.arb" "$work/real-en.after-add" && cmp -s "$real/app_fr.arb" "$work/real-fr.after-add" \
    && pass "identical re-run on real ARB copies does not change bytes" \
    || fail "real identical re-run mutated bytes"
else
  fail "real identical re-run exited non-zero: $(cat "$work/real-noop.err")"
fi

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures l10n tool shell test(s) failed" >&2
  exit 1
fi
echo "all l10n tool shell tests passed"
