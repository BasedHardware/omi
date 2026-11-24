#!/usr/bin/env bash
# CI-runnable emulator contract. Run from any directory.
set -euo pipefail
cd "${1:-$(dirname "$0")/../..}"
go_root=$PWD
python_bin=${REPLAY_PYTHON:-"$go_root/../backend/.venv/bin/python"}
test -x "$python_bin"
PYTHONPATH="$go_root/../backend" "$python_bin" -m unittest testing.finalization_replay.test_replay_contracts -v
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
commit=$(git -C "$go_root/.." rev-parse HEAD)

./scripts/with-postgres.sh ./scripts/with-firestore.sh bash -euc '
    scratch=$1
    python_bin=$2
    commit=$3
    repo_go=$PWD
    cd "$scratch"
    run() {
        "$scratch/replay" -jobd "$scratch/jobd" -python "$python_bin" -commit "$commit" "$@"
    }

    parity_status=0
    run -corpus "$repo_go"/tools/replay/corpus/admission-parity.json -output "$scratch/parity.json" || parity_status=$?
    if [[ $parity_status == 1 && -f "$scratch/parity.json" ]]; then
        echo "Admission parity unexplained rows (case, path, kind):" >&2
        "$python_bin" - "$scratch/parity.json" <<\PY
import json
import sys

with open(sys.argv[1], encoding="utf-8") as report_file:
    report = json.load(report_file)

printed = 0
for case in report.get("cases", []):
    for difference in case.get("differences", []):
        if difference.get("reason"):
            continue
        print(
            "{}: {} [{}]".format(
                case.get("name", "<unknown>"),
                difference.get("path", "<unknown>"),
                difference.get("kind", "<unknown>"),
            ),
            file=sys.stderr,
        )
        printed += 1
if printed == 0:
    print("none", file=sys.stderr)
PY
    fi
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
    run -corpus "$repo_go"/tools/replay/corpus/conformance-gaps.json -output "$scratch/gaps.json" -include-values || drift_status=$?
    if [[ -n "${REPLAY_TASK_OUTPUT_DIR:-}" ]]; then
        if [[ $drift_status != 0 && $drift_status != 1 ]]; then
            echo "Active replay failed to produce a classifiable report (exit $drift_status)" >&2
            exit 1
        fi
        # The verifier checks departures before exporting the value-free task reports.
        "$python_bin" -O "$repo_go/tools/replay/verify.py" --task-output "$REPLAY_TASK_OUTPUT_DIR" "$scratch/parity.json" "$scratch/gaps.json"
    else
        if [[ $drift_status != 1 ]]; then
            echo "Expected active conformance replay to report drift, got exit $drift_status" >&2
            exit 1
        fi

        "$python_bin" -O "$repo_go/tools/replay/verify.py" "$scratch/parity.json" "$scratch/gaps.json"
    fi
    "$python_bin" -O "$repo_go/tools/replay/verify.py" --mutation-check "$scratch/gaps.json"
' bash "$scratch" "$python_bin" "$commit"
