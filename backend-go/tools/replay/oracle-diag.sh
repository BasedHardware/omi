#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo 'usage: oracle-diag.sh WORKERD_REF OUTPUT' >&2
    exit 2
fi
worker_ref=$1
output=$2
if [[ ! $worker_ref =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo 'WORKERD_REF must be a full commit SHA' >&2
    exit 2
fi

repo=$(git rev-parse --show-toplevel)
worker_ref=$(git rev-parse --verify "${worker_ref}^{commit}")
if ! git cat-file -e "${worker_ref}:backend-go/cmd/workerd/ordinary_sync_replay_test.go" 2>/dev/null; then
    echo 'WORKERD_REF does not contain TestOrdinarySyncReplay' >&2
    exit 2
fi
if ! git show "${worker_ref}:backend-go/cmd/workerd/ordinary_sync_replay_test.go" | grep -q 'func TestOrdinarySyncReplay'; then
    echo 'WORKERD_REF does not contain the ordinary-sync replay seam' >&2
    exit 2
fi

output=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$output")
if [[ -e $output ]]; then
    echo "diagnostic report already exists: $output" >&2
    exit 2
fi
mkdir -p "$(dirname "$output")"

temporary=$(mktemp -d "${TMPDIR:-/tmp}/omi-oracle-diag.XXXXXXXX")
worker_tree="$temporary/workerd"
cleanup() {
    git -C "$repo" worktree remove --force "$worker_tree" >/dev/null 2>&1 || true
    rm -rf -- "$temporary"
}
trap cleanup EXIT

git -C "$repo" worktree add --quiet --detach "$worker_tree" "$worker_ref"
worker_backend="$worker_tree/backend"
python_bin="$repo/backend/.venv/bin/python"
if [[ ! -x $python_bin ]]; then
    echo "backend interpreter not found: $python_bin" >&2
    exit 2
fi

(
    cd "$worker_tree/backend-go"
    GOTOOLCHAIN=auto go test -c -o "$temporary/workerd.test" ./cmd/workerd
)

(
    cd "$repo/backend"
    PYTHONPATH="$repo/backend:$worker_backend" "$python_bin" -B -m testing.finalization_replay.ordinary_sync_diag \
        --worker-binary "$temporary/workerd.test" \
        --worker-backend "$worker_backend" \
        < "$repo/backend-go/tools/replay/corpus/conformance-gaps.json" \
        > "$temporary/observations.json"
)

set +e
(
    cd "$repo/backend-go"
    GOTOOLCHAIN=auto go run ./tools/replay \
        -observations "$temporary/observations.json" \
        -corpus tools/replay/corpus/conformance-gaps.json \
        -backend "$repo/backend" \
        -output "$output" \
        -commit "$worker_ref"
)
compare_status=$?
set -e
if [[ ! -s $output ]]; then
    echo "diagnostic comparison did not produce a report (status $compare_status)" >&2
    exit 2
fi
if [[ $compare_status -gt 2 ]]; then
    echo "diagnostic comparison failed unexpectedly (status $compare_status)" >&2
    exit 2
fi

"$python_bin" -I "$repo/backend/testing/finalization_replay/ordinary_sync_diag_report.py" "$output"
echo "Ordinary-sync diagnostic complete for $worker_ref; this target is not the lane 7 gate."
