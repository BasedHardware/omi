#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fixture="$(mktemp -d "${TMPDIR:-/tmp}/omi-ios-physical-auth-test.XXXXXX")"
trap 'rm -rf "$fixture"' EXIT

mkdir -p "$fixture/lib" "$fixture/ios/Config/Dev"

write_valid_fixture() {
  cat >"$fixture/.dev.env" <<'EOF'
API_BASE_URL=https://api.omiapi.com/
USE_WEB_AUTH=true
USE_AUTH_CUSTOM_TOKEN=true
EOF
  cat >"$fixture/lib/firebase_options_dev.dart" <<'EOF'
class DefaultFirebaseOptions {
  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'fixture',
    appId: '1:123:ios:fixture',
    projectId: 'based-hardware',
  );
}
EOF
  python3 - "$fixture/ios/Config/Dev/GoogleService-Info.plist" <<'PY'
import plistlib
import sys
from pathlib import Path

with Path(sys.argv[1]).open("wb") as stream:
    plistlib.dump(
        {
            "PROJECT_ID": "based-hardware",
            "GOOGLE_APP_ID": "1:123:ios:fixture",
        },
        stream,
    )
PY
  python3 - "$fixture/lib/env/dev_env.g.dart" <<'PY'
import sys
from pathlib import Path

url = "https://api.omiapi.com/"
keys = [0] * len(url)
data = [ord(char) for char in url]
Path(sys.argv[1]).parent.mkdir(parents=True, exist_ok=True)
Path(sys.argv[1]).write_text(
    "static const List<int> _enviedkeyapiBaseUrl = <int>["
    + ",".join(map(str, keys))
    + "];\n"
    + "static const List<int> _envieddataapiBaseUrl = <int>["
    + ",".join(map(str, data))
    + "];\n",
    encoding="utf-8",
)
PY
}

expect_failure() {
  if OMI_PHYSICAL_TEST_APP_ROOT="$fixture" \
    bash "$script_dir/verify_ios_physical_test_auth_config.sh" >/dev/null 2>&1; then
    echo "expected iOS physical-test auth preflight failure" >&2
    exit 1
  fi
}

write_valid_fixture
OMI_PHYSICAL_TEST_APP_ROOT="$fixture" \
  bash "$script_dir/verify_ios_physical_test_auth_config.sh" >/dev/null

sed -i.bak 's#https://api.omiapi.com/##' "$fixture/.dev.env"
expect_failure
rm -f "$fixture/.dev.env.bak"

write_valid_fixture
python3 - "$fixture/ios/Config/Dev/GoogleService-Info.plist" <<'PY'
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open("rb") as stream:
    config = plistlib.load(stream)
config["PROJECT_ID"] = "based-hardware-dev"
with path.open("wb") as stream:
    plistlib.dump(config, stream)
PY
expect_failure

write_valid_fixture
python3 - "$fixture/ios/Config/Dev/GoogleService-Info.plist" <<'PY'
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open("rb") as stream:
    config = plistlib.load(stream)
config["GOOGLE_APP_ID"] = "1:123:android:fixture"
with path.open("wb") as stream:
    plistlib.dump(config, stream)
PY
expect_failure

write_valid_fixture
sed -i.bak "s/projectId: 'based-hardware'/projectId: 'based-hardware-dev'/" \
  "$fixture/lib/firebase_options_dev.dart"
expect_failure
rm -f "$fixture/lib/firebase_options_dev.dart.bak"

write_valid_fixture
sed -i.bak "s/:ios:/:android:/" "$fixture/lib/firebase_options_dev.dart"
expect_failure
rm -f "$fixture/lib/firebase_options_dev.dart.bak"

write_valid_fixture
python3 - "$fixture/lib/env/dev_env.g.dart" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
path.write_text(
    re.sub(
        r"(_envieddataapiBaseUrl = <int>)\[[^\]]*\]",
        r"\1[]",
        source,
    ),
    encoding="utf-8",
)
PY
expect_failure

echo "iOS physical-test auth preflight tests: PASS"
