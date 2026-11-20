#!/usr/bin/env bash
# CI-runnable emulator contract. Run from any directory.
set -euo pipefail
cd "$(dirname "$0")/../.."
go_root=$PWD
python_bin=${REPLAY_PYTHON:-"$go_root/../backend/.venv/bin/python"}
test -x "$python_bin"
export TEST_FIRESTORE_REQUIRED=1

scratch=$(mktemp -d "${TMPDIR:-/tmp}/finalization-replay.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
go build -o "$scratch/jobd" ./cmd/jobd
go build -o "$scratch/replay" ./tools/replay

./scripts/with-postgres.sh ./scripts/with-firestore.sh bash -euc '
    scratch=$1
    python_bin=$2
    repo_go=$PWD
    cd "$scratch"
    run() {
        "$scratch/replay" -jobd "$scratch/jobd" -python "$python_bin" "$@"
    }

    run -corpus "$repo_go"/tools/replay/corpus/admission-parity.json -output "$scratch/parity.json"

    drift_status=0
    run -corpus "$repo_go"/tools/replay/corpus/conformance-gaps.json -output "$scratch/gaps.json" -include-values || drift_status=$?
    if [[ $drift_status != 1 ]]; then
        echo "Expected active conformance replay to report drift, got exit $drift_status" >&2
        exit 1
    fi

    "$python_bin" -O "$repo_go/tools/replay/verify.py" "$scratch/parity.json" "$scratch/gaps.json"
' bash "$scratch" "$python_bin"
