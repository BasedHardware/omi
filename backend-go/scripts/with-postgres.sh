#!/bin/bash
# with-postgres.sh CMD...: run CMD with TEST_DATABASE_URL pointing at a Postgres 16 server.
#
# If TEST_DATABASE_URL is already set, CMD runs against it. Otherwise this starts a private
# server in a temporary directory on a free port, runs CMD, and removes the server on any
# exit. Each test creates its own database on it (internal/platform/pgtest), so several
# checkouts can run this at once.
set -euo pipefail

export TEST_DATABASE_REQUIRED=1
if [[ -n ${TEST_DATABASE_URL:-} ]]; then
    exec "$@"
fi

bin=
for dir in "${PG_BIN:-}" "$(dirname "$(command -v pg_ctl 2>/dev/null || true)")" \
    /opt/homebrew/opt/postgresql@16/bin /usr/lib/postgresql/16/bin /usr/local/opt/postgresql@16/bin; do
    if [[ -n $dir && -x $dir/pg_ctl && -x $dir/initdb ]]; then
        bin=$dir
        break
    fi
done
if [[ -z $bin ]]; then
    cat >&2 <<'MSG'
with-postgres.sh: no Postgres 16 found. Database tests are part of the check and are not skipped.
Either install Postgres 16 (macOS: brew install postgresql@16) or point at a running server:
  TEST_DATABASE_URL=postgres://user:pass@host:5432/postgres?sslmode=disable make check
MSG
    exit 2
fi

data=$(mktemp -d "${TMPDIR:-/tmp}/backend-go-pg.XXXXXXXX")
started=
cleanup() {
    ret=$?
    trap - EXIT
    if [[ -n $started ]]; then
        "$bin/pg_ctl" -D "$data" -m immediate -w stop >/dev/null 2>&1 || ret=1
    fi
    rm -rf -- "$data"
    exit "$ret"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export LC_ALL=${LC_ALL:-en_US.UTF-8}
"$bin/initdb" -D "$data" -U postgres --auth=trust -E UTF8 >"$data.log" 2>&1 || { cat "$data.log" >&2; rm -f "$data.log"; exit 1; }
rm -f "$data.log"
# A free port chosen by the kernel, then handed to Postgres. The socket stays in the data
# directory so two servers never share a path.
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
"$bin/pg_ctl" -D "$data" -w -l "$data/server.log" \
    -o "-p $port -c listen_addresses=127.0.0.1 -c unix_socket_directories=$data -c fsync=off -c max_connections=300" \
    start >/dev/null || { cat "$data/server.log" >&2; exit 1; }
started=1
export TEST_DATABASE_URL="postgres://postgres@127.0.0.1:$port/postgres?sslmode=disable"
"$@"
