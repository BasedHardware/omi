#!/bin/bash
# Swarm wave launcher — gives the manager a blocking primitive (wave-1 lesson).
#
#   run-wave.sh start <manifest.json> <outdir>   launch all workers, detached
#   run-wave.sh wait <outdir> [timeoutSec]       block until all exit (default 540s);
#                                                exit 0 = all done, 3 = still running
#   run-wave.sh status <outdir>                  one line per worker
#
# Manifest: [{"name": "...", "model": "...", "brief": "/abs/path/brief.md"}, ...]
# Per worker, outdir gets: <name>.chatid  <name>.pid  <name>.out  <name>.exit
# Workers are told to write <outdir>/<name>.REPORT.json themselves (brief convention).
set -euo pipefail

cmd="${1:?start|wait|status}"

case "$cmd" in
  start)
    manifest="${2:?manifest.json}"; outdir="${3:?outdir}"
    mkdir -p "$outdir"
    count=$(python3 -c "import json;print(len(json.load(open('$manifest'))))")
    for i in $(seq 0 $((count - 1))); do
      name=$(python3 -c "import json;print(json.load(open('$manifest'))[$i]['name'])")
      model=$(python3 -c "import json;print(json.load(open('$manifest'))[$i]['model'])")
      brief=$(python3 -c "import json;print(json.load(open('$manifest'))[$i]['brief'])")
      chat=$(agent create-chat 2>/dev/null | tail -1)
      echo "$chat" > "$outdir/$name.chatid"
      (
        agent -p --trust --force --resume "$chat" --model "$model" "$(cat "$brief")" \
          > "$outdir/$name.out" 2>&1
        echo $? > "$outdir/$name.exit"
      ) &
      echo $! > "$outdir/$name.pid"
      echo "launched $name model=$model chat=$chat pid=$!"
    done
    ;;
  wait)
    outdir="${2:?outdir}"; timeout="${3:-540}"
    elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
      running=0
      for pidfile in "$outdir"/*.pid; do
        [ -e "$pidfile" ] || continue
        name=$(basename "$pidfile" .pid)
        [ -e "$outdir/$name.exit" ] && continue
        kill -0 "$(cat "$pidfile")" 2>/dev/null && running=$((running + 1)) || echo "-1" > "$outdir/$name.exit"
      done
      [ "$running" -eq 0 ] && { echo "all workers done"; exit 0; }
      sleep 15; elapsed=$((elapsed + 15))
    done
    echo "still running after ${timeout}s"; exit 3
    ;;
  status)
    outdir="${2:?outdir}"
    for chatfile in "$outdir"/*.chatid; do
      [ -e "$chatfile" ] || continue
      name=$(basename "$chatfile" .chatid)
      if [ -e "$outdir/$name.exit" ]; then state="exited($(cat "$outdir/$name.exit"))"
      elif kill -0 "$(cat "$outdir/$name.pid" 2>/dev/null)" 2>/dev/null; then state="running"
      else state="unknown"; fi
      echo "$name: $state chat=$(cat "$chatfile") out=$(wc -c < "$outdir/$name.out" 2>/dev/null || echo 0)B"
    done
    ;;
  *) echo "unknown command: $cmd" >&2; exit 2 ;;
esac
