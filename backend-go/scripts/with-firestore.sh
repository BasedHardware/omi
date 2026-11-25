#!/bin/bash
# with-firestore.sh CMD...: run CMD with FIRESTORE_EMULATOR_HOST pointing at a Firestore emulator.
#
# If FIRESTORE_EMULATOR_HOST is already set, CMD runs against it. Otherwise this starts a
# private emulator on a free port (firebase-tools and Java are needed), runs CMD, and stops
# the emulator on any exit. Each test uses its own project id, so runs do not share data.
#
# Without the tools, CMD still runs and the emulator tests skip with a notice, unless
# TEST_FIRESTORE_REQUIRED=1 (CI sets it): few packages touch Firestore, and not every
# machine has Java, so a missing emulator must not block unrelated work.
set -euo pipefail

if [[ -n ${FIRESTORE_EMULATOR_HOST:-} ]]; then
    export TEST_FIRESTORE_REQUIRED=1
    exec "$@"
fi
if ! command -v firebase >/dev/null 2>&1 || ! java -version >/dev/null 2>&1; then
    if [[ ${TEST_FIRESTORE_REQUIRED:-} == 1 ]]; then
        echo "with-firestore.sh: firebase-tools and Java are required (TEST_FIRESTORE_REQUIRED=1)" >&2
        exit 2
    fi
    cat >&2 <<'MSG'
with-firestore.sh: NOTICE: no Firestore emulator (needs firebase-tools and Java).
  Tests that write to Firestore will SKIP in this run. CI runs them.
  If you changed internal/platform/docstore or an adapter that uses it, run this where the
  emulator is available before pushing: npm install -g firebase-tools@15, and a JDK 21.
MSG
    exec "$@"
fi

work=$(mktemp -d "${TMPDIR:-/tmp}/backend-go-fs.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
printf '{"emulators":{"firestore":{"host":"127.0.0.1","port":%s},"ui":{"enabled":false},"singleProjectMode":false}}\n' \
    "$port" >"$work/firebase.json"
# emulators:exec takes one shell string: write the command to a file so its arguments
# keep their quoting.
{
    printf '#!/bin/bash\nexport TEST_FIRESTORE_REQUIRED=1\ncd %q\nexec' "$PWD"
    printf ' %q' "$@"
    printf '\n'
} >"$work/run.sh"
chmod +x "$work/run.sh"
# Run from the scratch directory: the emulator writes its debug log to the current directory.
cd "$work"
firebase --config "$work/firebase.json" emulators:exec --only firestore --project demo-backend-go "$work/run.sh"
