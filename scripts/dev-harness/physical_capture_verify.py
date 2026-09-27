#!/usr/bin/env python3
"""Offline consistency oracle for copied *real app* capture recovery evidence.

Does not boot/install an app, contact a backend, or certify hardware execution.
See physical_capture.md for the producer contract and remaining device gates.
"""

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=unique)


def child(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute(), "relative artifact path required")
    candidate = root / name
    require(".." not in Path(name).parts, "artifact traversal refused")
    require(not any(p.is_symlink() for p in [candidate, *candidate.parents] if p != root.parent),
            "symlink artifacts refused")
    require(candidate.resolve().is_relative_to(root.resolve()), "artifact escapes evidence directory")
    return candidate


def private_url(value):
    uri = urlsplit(value)
    require(uri.scheme in ("http", "https") and not uri.username and not uri.password,
            "private HTTP endpoint required")
    require(not uri.query and not uri.fragment and uri.path in ("", "/"), "base endpoint required")
    try:
        address = ipaddress.ip_address(uri.hostname or "")
    except ValueError as error:
        raise EvidenceError("literal private endpoint required; DNS is not isolation evidence") from error
    networks = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "::1/128")
    require(any(address in ipaddress.ip_network(network) for network in networks), "public endpoint refused")
    require(uri.port is not None, "explicit session port required")


def inventory(root, relative_directory, ids, owner):
    directory = child(root, relative_directory)
    rows = read_json(child(directory, "wals.json"))["wals"]
    require(isinstance(rows, list), "wals must be a list")
    indexed = {}
    for row in rows:
        key = f"{row['device']}_{row['timer_start']}"
        require(key not in indexed, "duplicate WAL identity")
        indexed[key] = row
    require(set(ids).issubset(indexed), "selected WAL missing from persisted inventory")
    result = {}
    for key in ids:
        row = indexed[key]
        require(row.get("owner_uid") == owner, "WAL owner differs from synthetic principal")
        require(row.get("storage") == "disk", "selected WAL is not on disk")
        name = row.get("file_path")
        require(isinstance(name, str) and name.endswith(".bin"), "WAL audio filename required")
        # Shipping Wal.getFilePath deliberately rebases old container paths.
        filename = Path(name).name
        data = child(directory, filename).read_bytes()
        require(len(data) > 0, "empty WAL audio")
        result[key] = {
            "file": filename,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "status": row["status"],
            "job_id": row.get("job_id"),
            "codec": row.get("codec"),
            "sample_rate": row.get("sample_rate"),
            "channel": row.get("channel"),
        }
    return result


def verify(manifest_path):
    root = manifest_path.resolve().parent
    manifest = read_json(manifest_path)
    require(manifest["schema"] == "physical-capture-recovery-v1", "wrong evidence schema")
    require(manifest["profile"] == "local_dev" and manifest["flavor"] == "dev", "dev/local_dev required")
    require(".capture-qualification." in manifest["bundle_id"], "separate qualification bundle required")
    require(re.fullmatch(r"[0-9a-f]{40}", manifest["source_sha"]) is not None, "source SHA required")
    require(re.fullmatch(r"[0-9a-f]{64}", manifest["dirty_input_sha256"]) is not None, "dirty input digest required")
    artifact = child(root, manifest["artifact"])
    require(hashlib.sha256(artifact.read_bytes()).hexdigest() == manifest["artifact_sha256"], "build artifact hash mismatch")
    private_url(manifest["api_base_url"])
    private_url(manifest["auth_emulator_url"])
    owner = manifest["synthetic_uid"]
    require(isinstance(owner, str) and owner.startswith("omi-physical-fixture-"), "synthetic principal required")
    ids = manifest["wal_ids"]
    require(isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids), "nonempty WAL selection required")
    require(len(set(ids)) == len(ids), "duplicate selected WAL")
    lifecycle = read_json(child(root, manifest["lifecycle"]))
    require(lifecycle["bundle_id"] == manifest["bundle_id"], "lifecycle bundle mismatch")
    # A PID alone is reusable. Producer must record launch identities from
    # process start time plus app boot nonce, with independently observed exit.
    before = lifecycle["before_process"]
    after = lifecycle["after_process"]
    require(all(isinstance(v, str) and v for v in [before, after]) and before != after,
            "distinct cold process identities required")
    require(lifecycle["observed_exit"] is True, "process termination not observed")
    times = [lifecycle[k] for k in ("persisted_at_ms", "terminated_at_ms", "relaunched_at_ms", "recovered_at_ms", "uploaded_at_ms", "completed_at_ms")]
    require(all(type(t) is int and t > 0 for t in times) and all(a < b for a, b in zip(times, times[1:])),
            "strict lifecycle chronology required")
    phases = {phase: inventory(root, manifest[phase], ids, owner)
              for phase in ("before", "recovered", "uploaded", "completed")}
    server = read_json(child(root, manifest["server_receipt"]))
    require(server["synthetic_uid"] == owner and server["api_base_url"] == manifest["api_base_url"], "server receipt ownership mismatch")
    require(server["status"] == "completed" and server["http_status"] == 202, "async upload and completed job required")
    require(len(server["files"]) == len(ids), "server receipt must cover exactly the selected WALs")
    for key in ids:
        first = phases["before"][key]
        require(first["status"] == "miss", "before snapshot must contain finalized unsynced WAL")
        for phase in phases:
            actual = phases[phase][key]
            require(all(actual[field] == first[field] for field in ("file", "bytes", "sha256", "codec", "sample_rate", "channel")),
                    "WAL bytes or decoding metadata changed across recovery/upload")
        require(phases["recovered"][key]["status"] == "miss", "recovery must precede upload")
        require(phases["uploaded"][key]["status"] == "uploaded", "202 is not terminal sync")
        require(phases["completed"][key]["status"] == "synced", "completed job not reflected in app WAL")
        matches = [f for f in server["files"] if f.get("filename") == first["file"]]
        require(len(matches) == 1 and matches[0].get("sha256") == first["sha256"] and matches[0].get("bytes") == first["bytes"],
                "server did not acknowledge exact persisted audio bytes")
        # Production syncWal uploads separately, so different WALs may have
        # different jobs. A shared top-level ID remains valid for batch uploads.
        job = matches[0].get("job_id", server.get("job_id"))
        require(isinstance(job, str) and job, "per-file server job identity required")
        require(phases["uploaded"][key]["job_id"] == job, "uploaded WAL job mismatch")
    return {"status": "artifact_consistency_passed", "recordings": len(ids), "hardware_qualified": False,
            "scope": "Copied artifacts agree; device provenance, bridge execution, audio quality and egress require separate evidence."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.manifest)
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # Never echo caller-controlled paths, identifiers, or JSON values.
        print(json.dumps({"status": "refused", "error_type": type(error).__name__, "hardware_qualified": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
