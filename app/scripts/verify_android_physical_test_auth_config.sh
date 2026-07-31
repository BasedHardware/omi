#!/usr/bin/env bash
set -euo pipefail

app_root="${OMI_PHYSICAL_TEST_APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091 # Resolved relative to this script at runtime.
source "$script_dir/physical_test_customer_plane.sh"
env_file="$app_root/.dev.env"
firebase_dart="$app_root/lib/firebase_options_dev.dart"
prod_firebase_dart="$app_root/lib/firebase_options_prod.dart"
google_services="$app_root/android/app/src/dev/google-services.json"
generated_env="$app_root/lib/env/dev_env.g.dart"
key_properties="$app_root/android/key.properties"
debug_keystore="$app_root/setup/prebuilt/debug.keystore"

fail() {
  echo "Android physical-test auth preflight FAILED: $*" >&2
  exit 1
}

for required in \
  "$env_file" \
  "$firebase_dart" \
  "$prod_firebase_dart" \
  "$google_services" \
  "$generated_env" \
  "$key_properties" \
  "$debug_keystore"; do
  [[ -f "$required" ]] || fail "missing $required"
done

grep -Fxq 'keyAlias=androiddebugkey' "$key_properties" ||
  fail "android/key.properties does not select the shared debug alias"
grep -Fxq 'storeFile=../../setup/prebuilt/debug.keystore' "$key_properties" ||
  fail "android/key.properties does not select the shared physical-test keystore"

api_base_url="$(awk -F= '$1 == "API_BASE_URL" { print substr($0, index($0, "=") + 1) }' "$env_file")"
[[ "$api_base_url" == "$OMI_PHYSICAL_TEST_API_BASE_URL" ]] ||
  fail ".dev.env targets '${api_base_url:-<empty>}' instead of the canonical customer API $OMI_PHYSICAL_TEST_API_BASE_URL"

python3 - "$google_services" "$firebase_dart" "$generated_env" \
  "$OMI_PHYSICAL_TEST_API_BASE_URL" "$OMI_PHYSICAL_TEST_FIREBASE_PROJECT_ID" <<'PY'
import json
import re
import sys
from pathlib import Path

google_services = Path(sys.argv[1])
firebase_dart = Path(sys.argv[2])
generated_env = Path(sys.argv[3])
expected_api_url = sys.argv[4]
expected_project_id = sys.argv[5]

config = json.loads(google_services.read_text(encoding="utf-8"))
project_id = config.get("project_info", {}).get("project_id")
packages = {
    client.get("client_info", {}).get("android_client_info", {}).get("package_name")
    for client in config.get("client", [])
}
if project_id != expected_project_id:
    raise SystemExit(
        "Android physical-test auth preflight FAILED: "
        f"google-services project is {project_id!r}, expected {expected_project_id!r}"
    )
if "com.friend.ios.dev" not in packages:
    raise SystemExit(
        "Android physical-test auth preflight FAILED: "
        "google-services has no com.friend.ios.dev client"
    )

source = firebase_dart.read_text(encoding="utf-8")
android_block = re.search(
    r"static const FirebaseOptions android = FirebaseOptions\((.*?)\n  \);",
    source,
    re.DOTALL,
)
if android_block is None or f"projectId: '{expected_project_id}'" not in android_block.group(1):
    raise SystemExit(
        "Android physical-test auth preflight FAILED: "
        "firebase_options_dev.dart Android options do not target based-hardware"
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
            "Android physical-test auth preflight FAILED: "
            f"generated dev env has no {name}"
        )
    return [int(value) for value in re.findall(r"\d+", match.group(1))]

keys = envied_ints("_enviedkeyapiBaseUrl")
data = envied_ints("_envieddataapiBaseUrl")
decoded_api_url = "".join(chr(value ^ keys[index]) for index, value in enumerate(data))
if decoded_api_url != expected_api_url:
    raise SystemExit(
        "Android physical-test auth preflight FAILED: "
        "generated dev_env.g.dart does not embed the production API; "
        "run `dart run build_runner clean` before regenerating"
    )
PY

echo "Android physical-test auth preflight: PASS (canonical production API + prod Firebase, dev package)"
