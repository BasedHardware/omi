#!/usr/bin/env bash
set -euo pipefail

app_root="${OMI_PHYSICAL_TEST_APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
env_file="$app_root/.dev.env"
firebase_dart="$app_root/lib/firebase_options_dev.dart"
google_services="$app_root/ios/Config/Dev/GoogleService-Info.plist"
generated_env="$app_root/lib/env/dev_env.g.dart"

fail() {
  echo "iOS physical-test auth preflight FAILED: $*" >&2
  exit 1
}

for required in "$env_file" "$firebase_dart" "$google_services" "$generated_env"; do
  [[ -f "$required" ]] || fail "missing $required"
done

api_base_url="$(awk -F= '$1 == "API_BASE_URL" { print substr($0, index($0, "=") + 1) }' "$env_file")"
[[ "$api_base_url" == "https://api.omiapi.com/" ]] ||
  fail ".dev.env targets '${api_base_url:-<empty>}' instead of the production API"

python3 - "$google_services" "$firebase_dart" "$generated_env" <<'PY'
import plistlib
import re
import sys
from pathlib import Path

google_services = Path(sys.argv[1])
firebase_dart = Path(sys.argv[2])
generated_env = Path(sys.argv[3])

with google_services.open("rb") as stream:
    config = plistlib.load(stream)

project_id = config.get("PROJECT_ID")
google_app_id = config.get("GOOGLE_APP_ID")
if project_id != "based-hardware":
    raise SystemExit(
        "iOS physical-test auth preflight FAILED: "
        f"GoogleService-Info project is {project_id!r}, expected 'based-hardware'"
    )
if not isinstance(google_app_id, str) or ":ios:" not in google_app_id:
    raise SystemExit(
        "iOS physical-test auth preflight FAILED: "
        "GoogleService-Info GOOGLE_APP_ID is not an iOS Firebase registration"
    )

source = firebase_dart.read_text(encoding="utf-8")
ios_block = re.search(
    r"static const FirebaseOptions ios = FirebaseOptions\((.*?)\n  \);",
    source,
    re.DOTALL,
)
if ios_block is None or "projectId: 'based-hardware'" not in ios_block.group(1):
    raise SystemExit(
        "iOS physical-test auth preflight FAILED: "
        "firebase_options_dev.dart iOS options do not target based-hardware"
    )
app_id_match = re.search(r"appId:\s*'([^']+)'", ios_block.group(1))
if app_id_match is None or ":ios:" not in app_id_match.group(1):
    raise SystemExit(
        "iOS physical-test auth preflight FAILED: "
        "firebase_options_dev.dart iOS appId is not an iOS Firebase registration"
    )

generated_source = generated_env.read_text(encoding="utf-8")


def envied_ints(name: str) -> list[int]:
    match = re.search(
        rf"static const List<int> {re.escape(name)} = <int>\[(.*?)\];",
        generated_source,
        re.DOTALL,
    )
    if match is None:
        raise SystemExit(
            "iOS physical-test auth preflight FAILED: "
            f"generated dev env has no {name}"
        )
    return [int(value) for value in re.findall(r"\d+", match.group(1))]


keys = envied_ints("_enviedkeyapiBaseUrl")
data = envied_ints("_envieddataapiBaseUrl")
decoded_api_url = "".join(chr(value ^ keys[index]) for index, value in enumerate(data))
if decoded_api_url != "https://api.omiapi.com/":
    raise SystemExit(
        "iOS physical-test auth preflight FAILED: "
        "generated dev_env.g.dart does not embed the production API; "
        "run `dart run build_runner clean` before regenerating"
    )
PY

echo "iOS physical-test auth preflight: PASS (generated prod API + prod Firebase, isolated dev app)"
