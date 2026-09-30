#!/usr/bin/env bash
# Build-source receipt shared by the desktop bundler and E2E verifier.

# Print the current repository identity as compact JSON. The working tree is
# evaluated from the repository top level so edits outside desktop/macos cannot
# be hidden by the caller's current directory.
omi_desktop_build_identity() {
  local repository_hint="$1"
  python3 - "$repository_hint" <<'PY'
import json
import subprocess
import sys


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", repository_hint, *args],
        check=False,
        capture_output=True,
        text=True,
    )


repository_hint = sys.argv[1]
top_level = git("rev-parse", "--show-toplevel")
revision_result = git("rev-parse", "--verify", "HEAD^{commit}")
if top_level.returncode != 0 or revision_result.returncode != 0:
    identity = {"schemaVersion": 1, "revision": "unknown", "workingTreeState": "unknown"}
else:
    repository_root = top_level.stdout.strip()
    revision = revision_result.stdout.strip().lower()
    status = subprocess.run(
        [
            "git",
            "-C",
            repository_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0 or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        identity = {"schemaVersion": 1, "revision": "unknown", "workingTreeState": "unknown"}
    else:
        identity = {
            "schemaVersion": 1,
            "revision": revision,
            "workingTreeState": "dirty" if status.stdout else "clean",
        }

print(json.dumps(identity, separators=(",", ":"), sort_keys=True))
PY
}

# Atomically stamp the source receipt into the bundle metadata. Rewriting the
# plist happens before codesigning on both full and incremental bundle paths.
omi_stamp_desktop_build_identity() {
  local repository_hint="$1"
  local plist_path="$2"
  local identity_json
  identity_json="$(omi_desktop_build_identity "$repository_hint")"

  python3 - "$plist_path" "$identity_json" <<'PY'
import json
import os
import plistlib
import stat
import sys
import tempfile


plist_path, identity_json = sys.argv[1:3]
identity = json.loads(identity_json)
with open(plist_path, "rb") as source:
    metadata = plistlib.load(source)

metadata["OMIBuildIdentitySchemaVersion"] = identity["schemaVersion"]
metadata["OMISourceRevision"] = identity["revision"]
metadata["OMISourceWorkingTreeState"] = identity["workingTreeState"]

directory = os.path.dirname(os.path.abspath(plist_path))
descriptor, temporary_path = tempfile.mkstemp(prefix=".omi-build-identity.", dir=directory)
try:
    with os.fdopen(descriptor, "wb") as destination:
        plistlib.dump(metadata, destination, sort_keys=False)
        destination.flush()
        os.fsync(destination.fileno())
    os.chmod(temporary_path, stat.S_IMODE(os.stat(plist_path).st_mode))
    os.replace(temporary_path, plist_path)
finally:
    if os.path.exists(temporary_path):
        os.unlink(temporary_path)
PY
}
