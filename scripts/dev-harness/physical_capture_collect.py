#!/usr/bin/env python3
"""Collect finalized-WAL recovery evidence from an already installed qualification app.

Default is an offline plan. --execute authorizes the exact bundle's kill/relaunch;
never installs an app, changes a service, or contacts an API.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import time
import urllib.parse
import zipfile

from physical_capture_verify import (
    EvidenceError,
    inventory,
    private_url,
    read_json,
    require,
    verify,
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def validate_artifact(artifact, receipt, bundle):
    require(
        receipt.get("built") is True and receipt.get("bundle_id") == bundle,
        "matching completed build required",
    )
    expected = receipt["signed_app_file_sha256"]
    with zipfile.ZipFile(artifact) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        require(
            len({info.filename for info in infos}) == len(infos),
            "duplicate archive entry",
        )
        plists = [
            info
            for info in infos
            if re.fullmatch(r"(?:Payload/)?[^/]+\.app/Info.plist", info.filename)
        ]
        require(len(plists) == 1, "one app archive required")
        prefix = plists[0].filename[: -len("Info.plist")]
        actual = {}
        for info in infos:
            require(
                info.filename.startswith(prefix)
                and ".." not in Path(info.filename).parts,
                "foreign archive entry",
            )
            require(
                (info.external_attr >> 16) & 0o170000 != 0o120000,
                "archive symlink refused",
            )
            actual[info.filename[len(prefix) :]] = hashlib.sha256(
                archive.read(info)
            ).hexdigest()
        require(actual == expected, "archive differs from signed build receipt")
        plist = plistlib.loads(archive.read(plists[0]))
    require(plist["CFBundleIdentifier"] == bundle, "artifact bundle mismatch")
    require(
        re.fullmatch(r"[A-Za-z0-9_-]+", plist["CFBundleExecutable"]),
        "unsafe executable",
    )
    return plist


class Device:
    def __init__(self, device, output):
        self.device, self.output, self.count = device, output, 0

    def call(self, args):
        self.count += 1
        path = self.output / f"devicectl-{self.count:03d}.json"
        command = [
            "xcrun",
            "devicectl",
            "device",
            *args,
            "--device",
            self.device,
            "--timeout",
            "30",
            "--json-output",
            str(path),
        ]
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("DEVICECTL_CHILD_")
        }
        started = time.time_ns() // 1000000
        result = subprocess.run(command, capture_output=True, timeout=40, env=env)
        require(
            result.returncode == 0 and path.is_file(),
            "devicectl failed; no lifecycle advancement",
        )
        payload = read_json(path)
        require(
            payload.get("info", {}).get("outcome") == "success",
            "devicectl unsuccessful",
        )
        save(
            self.output / f"operation-{self.count:03d}.json",
            {
                "device": self.device,
                "arguments": args,
                "started_at_ms": started,
                "finished_at_ms": time.time_ns() // 1000000,
                "result_file": path.name,
                "result_sha256": digest(path),
            },
        )
        return payload["result"]


class Collector:
    def __init__(self, args, device=None):
        self.a = args
        self.output = args.output.resolve()
        require(not self.output.exists(), "fresh output directory required")
        require(
            not any((p / ".git").exists() for p in [self.output, *self.output.parents]),
            "output must be outside Git",
        )
        require(
            re.fullmatch(
                r"[A-Za-z0-9.-]+\.capture-qualification\.[A-Za-z0-9.-]+", args.bundle_id
            ),
            "qualification bundle required",
        )
        require(
            re.fullmatch(r"[A-Fa-f0-9-]{16,64}", args.device),
            "explicit device identifier required",
        )
        self.receipt_bytes = args.build_receipt.read_bytes()
        self.receipt = read_json(args.build_receipt)
        require(
            args.build_receipt.read_bytes() == self.receipt_bytes,
            "build receipt changed during read",
        )
        self.plist = validate_artifact(args.artifact, self.receipt, args.bundle_id)
        self.defines = self.receipt["defines"]
        require(
            self.defines.get("OMI_APP_PROFILE") == "local_dev"
            and self.defines.get("OMI_PHYSICAL_QUALIFICATION") == "true",
            "physical local_dev build required",
        )
        self.uid = self.defines["OMI_PHYSICAL_FIXTURE_UID"]
        self.api = self.defines["OMI_API_BASE_URL"]
        self.auth = (
            "http://"
            + self.defines["OMI_FIREBASE_AUTH_EMULATOR_HOST"]
            + ":"
            + str(self.defines["OMI_FIREBASE_AUTH_EMULATOR_PORT"])
            + "/"
        )
        private_url(self.api)
        private_url(self.auth)
        self.run_path = args.server_receipts / "run.json"
        require(not self.run_path.is_symlink(), "run symlink refused")
        self.run = read_json(self.run_path)
        require(
            self.run.get("fixture_uid") == self.uid, "fixture run principal mismatch"
        )
        require(
            self.run.get("api_base_url") == self.api
            and self.run.get("auth_emulator_url") == self.auth,
            "fixture endpoints differ from artifact",
        )
        require(
            not (args.server_receipts / "host-upload-approved.json").exists(),
            "existing upload approval refused",
        )
        self.run_bytes = self.run_path.read_bytes()
        self.cutoff = self.run_path.stat().st_mtime_ns
        self.source = (
            "wearable"
            if self.defines.get("OMI_PHYSICAL_CAPTURE_SOURCE") == "wearable"
            or self.defines.get("OMI_PHYSICAL_WEARABLE_ID")
            else "phone_mic"
        )
        self.device = device
        self.deadline = time.monotonic() + args.timeout

    def pinned(self):
        require(
            self.run_path.read_bytes() == self.run_bytes,
            "fixture restarted during collection",
        )
        require(time.monotonic() < self.deadline, "collector deadline exceeded")

    def event(self, phase, process=None):
        while True:
            self.pinned()
            matches = []
            for path in self.a.server_receipts.glob("event-*.json"):
                if path.is_symlink() or path.stat().st_mtime_ns < self.cutoff:
                    continue
                try:
                    row = read_json(path)
                except (OSError, ValueError):
                    continue  # writer may still be flushing
                if (
                    row.get("fixture_uid") == self.uid
                    and row.get("run_id") == self.run["run_id"]
                    and row.get("phase") == phase
                    and (process is None or row.get("process") == process)
                ):
                    matches.append(row)
            require(len(matches) <= 1, "ambiguous phase events")
            if matches:
                save(self.output / f"event-{phase}.json", matches[0])
                return matches[0]
            time.sleep(1)

    def copy(self, source, destination):
        self.pinned()
        self.device.call(
            [
                "copy",
                "from",
                "--domain-type",
                "appDataContainer",
                "--domain-identifier",
                self.a.bundle_id,
                "--source",
                source,
                "--destination",
                str(destination),
            ]
        )
        require(
            destination.is_file() and not destination.is_symlink(),
            "device copy did not produce exact file",
        )

    def snapshot(self, phase, event, ids):
        folder = self.output / phase
        folder.mkdir()
        self.copy(f"Documents/physical_capture/{phase}/wals.json", folder / "wals.json")
        files = event.get("files")
        require(
            isinstance(files, list) and files and len(files) <= 64,
            "bounded snapshot files required",
        )
        require(
            {f["wal_id"] for f in files} == set(ids) and len(files) == len(ids),
            "event WAL selection mismatch",
        )
        for row in files:
            name = row["filename"]
            require(
                re.fullmatch(r"[A-Za-z0-9_.-]{1,240}\.bin", name), "unsafe WAL filename"
            )
            self.copy(f"Documents/physical_capture/{phase}/{name}", folder / name)
        actual = inventory(self.output, phase, ids, self.uid)
        for row in files:
            disk = actual[row["wal_id"]]
            require(
                all(disk[k] == row[k] for k in ("bytes", "sha256", "status", "job_id")),
                "event differs from independently copied WAL",
            )
            require(disk["file"] == row["filename"], "event filename mismatch")
        return actual

    def processes(self):
        return self.device.call(
            ["info", "processes", "--search", self.plist["CFBundleExecutable"]]
        )["runningProcesses"]

    def identify(self, event, executable):
        boot = event["process"]
        require(
            re.fullmatch(r"[1-9][0-9]*_[0-9]+", boot), "PID and boot nonce required"
        )
        pid = int(boot.split("_")[0])
        matches = [p for p in self.processes() if p["processIdentifier"] == pid]
        require(
            len(matches) == 1 and matches[0]["executable"] == executable,
            "PID does not own exact installed executable",
        )
        return pid

    def execute(self):
        self.output.mkdir(mode=0o700, parents=True)
        self.device = self.device or Device(self.a.device, self.output)
        shutil.copy2(self.a.artifact, self.output / "app.zip")
        shutil.copy2(self.a.build_receipt, self.output / "build-receipt.json")
        require(
            (self.output / "build-receipt.json").read_bytes() == self.receipt_bytes,
            "build receipt changed before collection",
        )
        validate_artifact(self.output / "app.zip", self.receipt, self.a.bundle_id)
        save(
            self.output / "build-identity.json",
            {
                "schema": "physical-capture-recorded-build-identity-v1",
                "scope": "entire recorded build receipt including Dart, native, defines and signed file hashes",
                "sha256": hashlib.sha256(
                    json.dumps(self.receipt, sort_keys=True).encode()
                ).hexdigest(),
            },
        )
        save(self.output / "fixture-run.json", self.run)
        before_event = self.event("awaiting_termination")
        boot = self.event("boot", before_event["process"])
        require(boot.get("source") == self.source, "source differs from build")
        self.copy(
            "Documents/physical_capture_state.json",
            self.output / "physical_capture_state.json",
        )
        state = read_json(self.output / "physical_capture_state.json")
        require(
            state["process"] == before_event["process"], "persisted process mismatch"
        )
        require(
            state.get("source") == self.source and state.get("fixture_uid") == self.uid,
            "persisted source/principal mismatch",
        )
        ids = state["wal_ids"]
        require(ids and len(ids) == len(set(ids)), "unique WAL IDs required")
        before = self.snapshot("before", before_event, ids)
        require(
            all(row["status"] == "miss" for row in before.values()),
            "WAL must be finalized unsynced",
        )
        persisted = time.time_ns() // 1000000
        apps = self.device.call(
            ["info", "apps", "--filter", f"bundleIdentifier == '{self.a.bundle_id}'"]
        )["apps"]
        require(
            len(apps) == 1 and apps[0]["bundleIdentifier"] == self.a.bundle_id,
            "exact installed app required",
        )
        app = apps[0]
        require(
            app.get("version") == self.plist["CFBundleShortVersionString"]
            and app.get("bundleVersion") == self.plist["CFBundleVersion"],
            "installed version mismatch",
        )
        url = urllib.parse.urlsplit(app["url"])
        require(
            url.scheme == "file"
            and not url.netloc
            and url.path.startswith("/private/var/containers/Bundle/Application/")
            and url.path.endswith(".app/"),
            "unexpected installed app URL",
        )
        executable = app["url"] + self.plist["CFBundleExecutable"]
        self.pinned()
        pid = self.identify(before_event, executable)
        self.device.call(["process", "terminate", "--pid", str(pid), "--kill"])
        while any(p["processIdentifier"] == pid for p in self.processes()):
            self.pinned()
            time.sleep(1)
        terminated = time.time_ns() // 1000000
        self.pinned()
        self.device.call(["process", "launch", self.a.bundle_id])
        relaunched = time.time_ns() // 1000000
        recovered_event = self.event("recovered")
        require(
            recovered_event["process"] != before_event["process"],
            "cold boot nonce unchanged",
        )
        self.identify(recovered_event, executable)
        recovered = self.snapshot("recovered", recovered_event, ids)
        require(recovered == before, "recovered WAL differs before upload approval")
        recovered_at = time.time_ns() // 1000000
        self.pinned()
        save(
            self.a.server_receipts / "host-upload-approved.json",
            {
                "command": "upload",
                "fixture_uid": self.uid,
                "run_id": self.run["run_id"],
            },
        )
        uploaded_event = self.event("uploaded", recovered_event["process"])
        uploaded = self.snapshot("uploaded", uploaded_event, ids)
        uploaded_at = time.time_ns() // 1000000
        completed_event = self.event("completed", recovered_event["process"])
        self.snapshot("completed", completed_event, ids)
        completed_at = time.time_ns() // 1000000
        jobs = {row["job_id"] for row in uploaded.values()}
        files = []
        for job in jobs:
            require(
                isinstance(job, str) and re.fullmatch(r"fixture-[0-9a-f]{32}", job),
                "fixture job identity required",
            )
            receipt = read_json(self.a.server_receipts / f"completed-{job}.json")
            require(
                receipt["run_id"] == self.run["run_id"]
                and receipt["job_id"] == job
                and receipt["status"] == "completed",
                "completed job run mismatch",
            )
            files.extend(receipt["files"])
            save(self.output / f"completed-{job}.json", receipt)
        save(
            self.output / "server.json",
            {
                "api_base_url": self.api,
                "synthetic_uid": self.uid,
                "http_status": 202,
                "status": "completed",
                "files": files,
            },
        )
        save(
            self.output / "lifecycle.json",
            {
                "bundle_id": self.a.bundle_id,
                "device": self.a.device,
                "before_process": before_event["process"],
                "after_process": recovered_event["process"],
                "observed_exit": True,
                "persisted_at_ms": persisted,
                "terminated_at_ms": terminated,
                "relaunched_at_ms": relaunched,
                "recovered_at_ms": recovered_at,
                "uploaded_at_ms": uploaded_at,
                "completed_at_ms": completed_at,
                "installed_executable": executable,
                "installed_binary_hash_independently_verified": False,
            },
        )
        manifest = {
            "schema": "physical-capture-recovery-v1",
            "profile": "local_dev",
            "flavor": "dev",
            "bundle_id": self.a.bundle_id,
            "source_sha": self.receipt["git_head"],
            "dirty_input_sha256": hashlib.sha256(
                json.dumps(self.receipt, sort_keys=True).encode()
            ).hexdigest(),
            "artifact": "app.zip",
            "artifact_sha256": digest(self.output / "app.zip"),
            "api_base_url": self.api,
            "auth_emulator_url": self.auth,
            "synthetic_uid": self.uid,
            "wal_ids": ids,
            "lifecycle": "lifecycle.json",
            "server_receipt": "server.json",
            **{
                phase: phase
                for phase in ("before", "recovered", "uploaded", "completed")
            },
        }
        save(self.output / "manifest.json", manifest)
        result = verify(self.output / "manifest.json")
        save(self.output / "verification.json", result)
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("device", "bundle-id"):
        p.add_argument("--" + flag, required=True)
    for flag in ("artifact", "build-receipt", "server-receipts", "output"):
        p.add_argument("--" + flag, type=Path, required=True)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    try:
        require(30 <= a.timeout <= 1800, "timeout must be 30..1800 seconds")
        collector = Collector(a)
        if not a.execute:
            print(
                json.dumps(
                    {
                        "mode": "plan",
                        "steps": [
                            "wait awaiting_termination",
                            "copy and verify finalized WAL",
                            "verify exact installed executable and PID",
                            "kill and independently observe exit",
                            "relaunch same bundle",
                            "copy and compare recovery",
                            "approve current-run upload",
                            "copy upload/completion and run oracle",
                        ],
                    }
                )
            )
            return 0
        print(json.dumps(collector.execute()))
        return 0
    except EvidenceError as error:
        print(
            json.dumps(
                {"status": "refused", "reason": str(error), "hardware_qualified": False}
            )
        )
        return 2
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ):
        print(json.dumps({"status": "refused", "hardware_qualified": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
