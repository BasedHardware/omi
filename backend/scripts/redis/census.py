#!/usr/bin/env python3
"""Prod Redis capacity census — runbook tool.

Produces the numbers behind backend capacity decisions: used memory vs the
known SKU ceiling, key count, and a full-keyspace prefix tally with byte,
max-key and TTL-shape aggregation.

Read-only against the data plane: SCAN, MEMORY USAGE, PTTL, INFO. The tally
scripts are `#!lua flags=allow-oom` so they still run at maxmemory; they never
write. Only derived aggregates print — never credential-adjacent INFO fields
or raw user-keyed names.

Usage (credentials from env or hostctl secrets):
    python3 backend/scripts/redis/census.py [--tally] [--deep]

- default: INFO memory + DBSIZE
- --tally: full-keyspace prefix key-count tally (time-budgeted Lua)
- --deep:  adds per-prefix summed/max MEMORY USAGE (one op per key; slow)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

MAXMEMORY_BYTES = 12 * 1024**3  # Redis Cloud Single-Zone_Persistence_12GB; INFO omits maxmemory
SCRIPTS = Path(__file__).resolve().parent
HOSTCTL_SECRETS = Path.home() / ".local/share/hostctl/secrets"


def _secret(name: str) -> str:
    value = os.environ.get(name.replace("-", "_").upper(), "")
    if value:
        return value
    try:
        return (HOSTCTL_SECRETS / name).read_text().strip()
    except OSError:
        return ""


def _cli(*args: str, timeout: int = 120) -> str:
    host = _secret("omi-redis-db-host")
    port = _secret("omi-redis-db-port") or "6379"
    password = _secret("omi-redis-db-password")
    if not (host and password):
        print(
            "ERROR: set REDIS_DB_HOST/REDIS_DB_PORT/REDIS_DB_PASSWORD env or hostctl secrets omi-redis-db-*",
            file=sys.stderr,
        )
        sys.exit(2)
    env = dict(os.environ, REDISCLI_AUTH=password)
    result = subprocess.run(
        ["redis-cli", "-h", host, "-p", port, "--no-auth-warning", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip().splitlines()[-1][:200])
    return result.stdout


def _info(section: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _cli("INFO", section).splitlines():
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def _eval_raw(script_path: Path, cursor: str) -> list[str]:
    out = _cli("--raw", "EVAL", script_path.read_text(), "1", cursor)
    return [line for line in out.splitlines() if line != ""]


def _is_num(text: str) -> bool:
    try:
        int(text)
        return True
    except ValueError:
        return False


def print_memory() -> None:
    memory = _info("memory")
    used = int(memory.get("used_memory", "0"))
    print(f"used_memory: {used:,} ({memory.get('used_memory_human', '?')})")
    print(f"SKU ceiling: {MAXMEMORY_BYTES:,} ({used / MAXMEMORY_BYTES * 100:.1f}% used)")
    print(f"peak:        {int(memory.get('used_memory_peak', '0')):,}")
    print(f"policy:      {memory.get('maxmemory_policy', 'omitted by Redis Cloud')}")


def print_keyspace() -> None:
    dbsize = _cli("DBSIZE").strip()
    print(f"DBSIZE: {int(dbsize):,}")


def prefix_tally() -> Counter[str]:
    """Full-keyspace prefix key-count tally via time-budgeted allow-oom Lua.

    Runs the server-side tally script repeatedly with client-supplied cursors
    until the keyspace is exhausted, then merges the per-iteration counts.
    """
    counts: Counter[str] = Counter()
    cursor = "0"
    total = 0
    while True:
        lines = _eval_raw(SCRIPTS / "prefix_tally.lua", cursor)
        if len(lines) < 4 or not _is_num(lines[0]):
            raise RuntimeError(f"unexpected tally output from server: {lines[:3]}")
        total += int(lines[0])
        cursor = lines[1]
        # --raw flattening of {total, cursor, iters, {{pfx, count}, ...}, {fat...}}:
        # idx0 total, idx1 cursor, idx2 iters, then alternating prefix/count
        # pairs, then the fat-key list.
        index = 3
        while index + 1 < len(lines) and not _is_num(lines[index]):
            if _is_num(lines[index + 1]):
                counts[lines[index]] += int(lines[index + 1])
            index += 2
            # The tail after pairs is the fat-key list: numeric count followed
            # by key strings. Pairs parsing naturally stops there because the
            # count is numeric in the prefix position.
        if cursor == "0":
            break
    print(f"tallied {total:,} keys across {len(counts)} prefixes (full keyspace)")
    return counts


def prefix_deep() -> dict[str, tuple[int, int, int]]:
    """Per-prefix {keys, summed bytes, max bytes} via deep_sample.lua.

    Returns aggregates keyed by prefix; sorted by summed bytes at print time.
    """
    agg: dict[str, list[int]] = {}
    big: list[tuple[int, str]] = []
    cursor = "0"
    while True:
        lines = _eval_raw(SCRIPTS / "deep_sample.lua", cursor)
        if len(lines) < 4 or not _is_num(lines[0]):
            raise RuntimeError(f"unexpected deep output from server: {lines[:3]}")
        cursor = lines[1]
        # --raw flattening of {total, cursor, iters, [[pfx,n,sum,max]...], [[mu,key]...]}:
        # idx0 total, idx1 cursor, idx2 iters, then 4-tuples until a number
        # appears in the prefix position, then (mu, key) pairs to the end.
        index = 3
        while index < len(lines) and not _is_num(lines[index]):
            if index + 3 < len(lines) and all(_is_num(lines[index + offset]) for offset in (1, 2, 3)):
                prefix = lines[index]
                entry = agg.setdefault(prefix, [0, 0, 0])
                entry[0] += int(lines[index + 1])
                entry[1] += int(lines[index + 2])
                entry[2] = max(entry[2], int(lines[index + 3]))
                index += 4
            else:
                break
        while index + 1 < len(lines):
            if _is_num(lines[index]):
                big.append((int(lines[index]), lines[index + 1]))
                index += 2
            else:
                index += 1
        if cursor == "0":
            break
    return {prefix: (entry[0], entry[1], entry[2]) for prefix, entry in agg.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tally", action="store_true", help="full-keyspace prefix key-count tally")
    parser.add_argument("--deep", action="store_true", help="per-prefix byte aggregation (slow)")
    args = parser.parse_args()

    print_memory()
    print_keyspace()

    if args.tally:
        counts = prefix_tally()
        for prefix, count in counts.most_common(25):
            print(f"{prefix:<28} {count:>12,}")
    if args.deep:
        deep = prefix_deep()
        used = int(_info("memory").get("used_memory", "1"))
        print(f"\n{'prefix':<28} {'keys':>10} {'GB':>7} {'%used':>6} {'maxKB':>8}")
        for prefix, (keys, total_bytes, max_bytes) in sorted(deep.items(), key=lambda item: -item[1][1])[:25]:
            print(
                f"{prefix:<28} {keys:>10,} {total_bytes / 1e9:>7.2f} {total_bytes / used * 100:>5.1f}% {max_bytes / 1024:>8.0f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
