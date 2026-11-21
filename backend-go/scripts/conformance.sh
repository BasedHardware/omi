#!/bin/bash
# conformance.sh public: run the kit's public black-box suite against bin/jobd.
# Starts a throwaway Postgres cluster and the kit's stub, and stops both on any exit.
set -euo pipefail

kit=${KIT:?set KIT to the conformance kit directory}
go_bin=${GO:-go}
name=${CONFORMANCE_CLUSTER:-backendgo}
base=${CONFORMANCE_PORT_BASE:-24600}
repo=$PWD
mkdir -p "$repo/.verify"
scratch=$(mktemp -d "$repo/.verify/run.XXXXXXXX")
stub_pid=
jobd_pid=
cluster_started=
cleanup() {
    ret=$?
    trap - EXIT
    for pid in "$jobd_pid" "$stub_pid"; do
        if [[ -n $pid ]]; then
            kill -TERM "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
    if [[ -n $cluster_started ]]; then
        "$kit/bin/pg-down" "$name" || ret=1
    fi
    if [[ $ret -ne 0 ]]; then
        printf 'Logs are in %s\n' "$scratch" >&2
    else
        rm -rf -- "$scratch"
    fi
    exit "$ret"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ ${1:-} == public ]] || { echo "usage: conformance.sh public" >&2; exit 2; }
export LC_ALL=${LC_ALL:-en_US.UTF-8}
export DATABASE_URL
DATABASE_URL=$("$kit/bin/pg-up" "$name" "$base" 2>"$scratch/postgres.log") || {
    cat "$scratch/postgres.log" >&2
    exit 1
}
cluster_started=1
"$go_bin" -C "$kit" build -o "$scratch/stub" ./stub
export STUB_URL=http://127.0.0.1:$((base + 1)) JOBD_URL=http://127.0.0.1:$((base + 2)) PORT=$((base + 2))
export ENCRYPTION_SECRET JOBD_BIN="$repo/bin/jobd" PYTHONDONTWRITEBYTECODE=1
ENCRYPTION_SECRET=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["test_secret"])' "$kit/vectors/vectors.json")
"$scratch/stub" -port $((base + 1)) >"$scratch/stub.log" 2>&1 &
stub_pid=$!
"$JOBD_BIN" migrate
"$JOBD_BIN" serve >"$scratch/jobd.log" 2>&1 &
jobd_pid=$!
for _ in $(seq 1 100); do
    curl -fsS -o /dev/null "$JOBD_URL/healthz" 2>/dev/null && break
    kill -0 "$jobd_pid" 2>/dev/null || { cat "$scratch/jobd.log" >&2; exit 1; }
    sleep 0.1
done
make -C "$kit" test-public
