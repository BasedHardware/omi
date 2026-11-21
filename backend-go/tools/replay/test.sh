#!/usr/bin/env bash
# CI-runnable emulator contract. Run from any directory.
set -euo pipefail
cd "$(dirname "$0")/../.."
go_root=$PWD
python_bin=${REPLAY_PYTHON:-"$go_root/../backend/.venv/bin/python"}
test -x "$python_bin"
export TEST_FIRESTORE_REQUIRED=1
task_report_dir=${REPLAY_TASK_OUTPUT_DIR:-}
if [[ -n "$task_report_dir" ]]; then
    mkdir -p "$task_report_dir"
    task_report_dir=$(cd "$task_report_dir" && pwd)
    case "$task_report_dir/" in
        "$go_root/"*) echo "task reports must be outside the Go checkout" >&2; exit 2 ;;
    esac
    REPLAY_TASK_OUTPUT_DIR=$task_report_dir
    export REPLAY_TASK_OUTPUT_DIR
fi

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

    parity_status=0
    run -corpus "$repo_go"/tools/replay/corpus/admission-parity.json -output "$scratch/parity.json" || parity_status=$?
    if [[ -n "${REPLAY_TASK_OUTPUT_DIR:-}" ]]; then
        if [[ $parity_status != 0 && $parity_status != 1 ]]; then
            echo "Parity replay failed to produce a classifiable report (exit $parity_status)" >&2
            exit 1
        fi
    elif [[ $parity_status != 0 ]]; then
        echo "Expected admission parity, got exit $parity_status" >&2
        exit 1
    fi

    drift_status=0
    if [[ -n "${REPLAY_TASK_OUTPUT_DIR:-}" ]]; then
        run -corpus "$repo_go"/tools/replay/corpus/conformance-gaps.json -output "$scratch/gaps.json" || drift_status=$?
    else
        run -corpus "$repo_go"/tools/replay/corpus/conformance-gaps.json -output "$scratch/gaps.json" -include-values || drift_status=$?
    fi
    if [[ -n "${REPLAY_TASK_OUTPUT_DIR:-}" ]]; then
        if [[ $drift_status != 0 && $drift_status != 1 ]]; then
            echo "Active replay failed to produce a classifiable report (exit $drift_status)" >&2
            exit 1
        fi
        cp "$scratch/parity.json" "$REPLAY_TASK_OUTPUT_DIR/parity.json"
        cp "$scratch/gaps.json" "$REPLAY_TASK_OUTPUT_DIR/gaps.json"
    else
        if [[ $drift_status != 1 ]]; then
            echo "Expected active conformance replay to report drift, got exit $drift_status" >&2
            exit 1
        fi

        "$python_bin" -O "$repo_go/tools/replay/verify.py" "$scratch/parity.json" "$scratch/gaps.json"
    fi
' bash "$scratch" "$python_bin"
