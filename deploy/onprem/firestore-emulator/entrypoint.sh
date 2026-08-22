#!/bin/sh
# Persist the default-baseline Firestore/Auth emulator state across `down`/`up` (cubic PR 10887
# review 4909186286 #3). The emulator is the default on-prem storage (ADR-0003; Mongo is the
# durable opt-in for production, ADR-0002). Without this its data lived only in the container and
# was lost on recreate.
#
# Import only when a prior export exists (a first run on a fresh volume has none, and firebase
# errors on --import of an empty dir), and always export on graceful shutdown.
#
# Docker sends SIGTERM on `stop`/`down`, but firebase-tools runs its --export-on-exit handler on
# SIGINT (Ctrl-C), not SIGTERM. So run firebase in the background, forward SIGTERM as SIGINT, and
# wait for the export to finish. The compose service sets a stop_grace_period long enough for it.

DATA_DIR=/data/emulator
mkdir -p "$DATA_DIR"

IMPORT_ARGS=""
if [ -f "$DATA_DIR/firebase-export-metadata.json" ]; then
    IMPORT_ARGS="--import=$DATA_DIR"
fi

firebase emulators:start --only firestore,auth --project demo-omi-local \
    $IMPORT_ARGS --export-on-exit="$DATA_DIR" &
child=$!

trap 'kill -INT "$child" 2>/dev/null' TERM INT

# First wait returns when the trapped signal is caught; the second waits for firebase to finish
# exporting and exit. Without a signal, the first returns on exit and the second is a no-op.
wait "$child"
wait "$child"
