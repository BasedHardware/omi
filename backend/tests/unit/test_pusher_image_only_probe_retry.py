"""SCA-4763: a read-only admission probe retries a stale snapshot; a write does not.

The post-move inverse probe runs immediately after the forward image patch, while the
Deployment's status is still being written for the rollout that patch started. Its
resourceVersion precondition fails on the already-stale snapshot, which is not an
admission refusal. Promotion runs 46148826874 and 46150013617 reversed on exactly that
race, so the probe re-reads and retries within a bound while the live write stays
single-attempt and strict.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import pusher_image_only as helper  # noqa: E402

BASELINE = helper.BASELINE
CANDIDATE = "gcr.io/based-hardware/pusher@sha256:" + "a" * 64


def resolve(obj, path):
    current = obj
    for part in path.strip("/").split("/"):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def assign(obj, path, value):
    parts = path.strip("/").split("/")
    parent = obj
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    key = parts[-1]
    if isinstance(parent, list):
        parent[int(key)] = value
    else:
        parent[key] = value


class FakeCluster:
    def __init__(self, *, fail_first=False, always_fail=False):
        self.target = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": helper.TARGET,
                "namespace": helper.NAMESPACE,
                "uid": "deploy-uid",
                "resourceVersion": "11",
            },
            "spec": {"template": {"spec": {"containers": [{"name": "pusher", "image": BASELINE}]}}},
        }
        self.fail_first = fail_first
        self.always_fail = always_fail
        self.calls = 0
        self.reads = 0

    def get(self, resource, name=None, *, namespace=None, optional=False):
        assert resource == "deployment.apps"
        self.reads += 1
        return copy.deepcopy(self.target)

    def call(self, *args, reason="kubernetes_read_failed", stdin=None):
        assert args[0] == "patch"
        self.calls += 1
        ops = json.loads(stdin)
        if self.always_fail or (self.fail_first and self.calls == 1):
            raise helper.Refused(reason)
        changed = copy.deepcopy(self.target)
        for op in ops:
            if op["op"] == "test":
                if resolve(changed, op["path"]) != op["value"]:
                    raise helper.Refused(reason)
            elif op["op"] == "replace":
                assign(changed, op["path"], op["value"])
        return changed


def test_read_only_probe_retries_a_stale_precondition_and_succeeds():
    cluster = FakeCluster(fail_first=True)

    admitted = helper.submit_image_patch(cluster, cluster.target, helper.TARGET, BASELINE, CANDIDATE, dry_run=True)

    assert cluster.calls == 2
    assert cluster.reads == 1  # re-read before the retry
    assert helper.image_of(admitted, helper.TARGET) == CANDIDATE


def test_read_only_probe_still_fails_closed_after_the_bound():
    cluster = FakeCluster(always_fail=True)

    with pytest.raises(helper.Refused, match="server_dry_run_rejected"):
        helper.submit_image_patch(cluster, cluster.target, helper.TARGET, BASELINE, CANDIDATE, dry_run=True)

    assert cluster.calls == 3


def test_live_write_is_never_retried():
    cluster = FakeCluster(always_fail=True)

    with pytest.raises(helper.Refused, match="live_patch_unconfirmed_reconcile_before_retry"):
        helper.submit_image_patch(cluster, cluster.target, helper.TARGET, BASELINE, CANDIDATE, dry_run=False)

    assert cluster.calls == 1
    assert cluster.reads == 0
