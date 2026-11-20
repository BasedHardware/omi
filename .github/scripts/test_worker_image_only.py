"""Offline behavioral fixtures for the SCA-2149 preservation primitive."""

import copy
import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import re
import subprocess
import sys

import yaml

import worker_image_only as worker


OLD = worker.REPOSITORY + "@sha256:" + "1" * 64
NEW = worker.REPOSITORY + "@sha256:" + "2" * 64


def deployment(name=worker.TARGET):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": worker.NAMESPACE, "uid": name + "-uid", "resourceVersion": "17"},
        "spec": {
            "replicas": 8,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"annotations": {"operator-owned": "preserve"}, "labels": {"app": name}},
                "spec": {
                    "serviceAccountName": "existing-worker",
                    "terminationGracePeriodSeconds": 1500,
                    "nodeSelector": {"pool": "gpu"},
                    "tolerations": [{"key": "gpu", "operator": "Exists", "effect": "NoSchedule"}],
                    "affinity": {"nodeAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": []}},
                    "volumes": [{"name": "runtime", "secret": {"secretName": "existing"}}],
                    "containers": [
                        {
                            "name": "worker",
                            "image": OLD,
                            "env": [
                                {"name": "FIRESTORE_READ_LEVERS", "value": "{}"},
                                {"name": "PRIVATE", "value": "do-not-print-this"},
                                {"name": "TOKEN", "valueFrom": {"secretKeyRef": {"name": "existing", "key": "token"}}},
                            ],
                            "resources": {"limits": {"nvidia.com/gpu": "1", "memory": "32Gi"}},
                            "volumeMounts": [{"name": "runtime", "mountPath": "/runtime", "readOnly": True}],
                        }
                    ],
                },
            },
        },
    }


THIRD = worker.REPOSITORY + "@sha256:" + "3" * 64


def cronjob(name):
    obj = deployment(name)
    obj["apiVersion"] = "batch/v1"
    obj["kind"] = "CronJob"
    obj["spec"] = {"schedule": "0 * * * *", "jobTemplate": {"spec": {"template": obj["spec"]["template"]}}}
    return obj


def hpa(target):
    return {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": target, "namespace": worker.NAMESPACE, "uid": target + "-hpa-uid"},
        "spec": {"scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": target},
                 "minReplicas": 1, "maxReplicas": 16},
    }


def job(name, owner=None):
    obj = deployment(name)
    obj["apiVersion"] = "batch/v1"
    obj["kind"] = "Job"
    source = owner["spec"]["jobTemplate"]["spec"]["template"] if owner is not None else obj["spec"]["template"]
    template = copy.deepcopy(source)
    # What the Job controller and API defaulting add to a CronJob-created run (live shape, 2026-11-19).
    uid = obj["metadata"]["uid"]
    template["metadata"]["labels"].update({"batch.kubernetes.io/job-name": name, "job-name": name,
                                           "batch.kubernetes.io/controller-uid": uid, "controller-uid": uid})
    obj["spec"] = {"template": template, "selector": {"matchLabels": {"batch.kubernetes.io/controller-uid": uid}},
                   **worker.JOB_DEFAULTED}
    if owner is not None:
        obj["metadata"]["ownerReferences"] = [
            {"apiVersion": "batch/v1", "kind": "CronJob", "name": owner["metadata"]["name"],
             "uid": owner["metadata"]["uid"], "controller": True}
        ]
    return obj


class Cluster:
    """Execute real JSON-patch tests/replacement against a mutable fake API object."""

    def __init__(self):
        self.target = deployment()
        self.siblings = [deployment("record-seal-worker"), deployment(worker.TARGET + "-t4")]
        self.siblings[-1]["spec"]["replicas"] = 0
        self.hpas = [hpa(worker.TARGET), hpa("record-seal-worker")]
        self.admission_mutates_on_write = False
        self.rescale_before_write = None
        self.deployment_reads = 0
        self.writes = 0
        self.drift_on_patch = False
        self.consumer_reads = 0
        self.drift_on_consumer_read = 0
        self.admission_mutates = False

    def __call__(self, *args):
        if args[0] == "get":
            if args[1] == "deployment":
                self.deployment_reads += 1
                # Fire on the read after deploy()'s snapshot: an HPA write lands before the fresh read.
                if self.rescale_before_write is not None and self.deployment_reads == 2:
                    self.target["spec"]["replicas"] = self.rescale_before_write
                    self.target["metadata"]["resourceVersion"] = "40"
                    self.rescale_before_write = None
                return copy.deepcopy(self.target)
            self.consumer_reads += 1
            if self.consumer_reads == self.drift_on_consumer_read:
                self.siblings[0]["spec"]["template"]["spec"]["serviceAccountName"] = "changed"
            return {"items": copy.deepcopy([self.target, *self.siblings, *self.hpas])}
        if self.drift_on_patch and "--dry-run=server" not in args:
            self.target["metadata"]["resourceVersion"] = "18"
        patch = json.loads(args[args.index("-p") + 1])
        candidate = copy.deepcopy(self.target)
        for op in patch:
            parent = candidate
            parts = op["path"].strip("/").split("/")
            for key in parts[:-1]:
                parent = parent[int(key)] if isinstance(parent, list) else parent[key]
            key = parts[-1]
            if op["op"] == "test":
                if parent[key] != op["value"]:
                    raise ValueError("API conflict")
            else:
                parent[key] = op["value"]
        if self.admission_mutates or (self.admission_mutates_on_write and "--dry-run=server" not in args):
            candidate["spec"]["replicas"] = 2
        if "--dry-run=server" not in args:
            self.target = candidate
            self.writes += 1
        return copy.deepcopy(candidate)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.cluster = Cluster()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.receipt_path = Path(self.tmp.name) / "receipt.json"
        self.baseline = worker.snapshot(self.cluster)[1]

    def deploy(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            receipt = worker.deploy(self.baseline, NEW, self.receipt_path, self.cluster)
        self.output = output.getvalue()
        return receipt

    def test_only_image_changes_and_empty_levers_valuefrom_and_all_runtime_fields_survive(self):
        original = copy.deepcopy(self.cluster.target)
        siblings = copy.deepcopy(self.cluster.siblings)
        receipt = self.deploy()
        worker.verify(receipt, self.cluster)
        self.cluster.target["spec"]["template"]["spec"]["containers"][0]["image"] = OLD
        self.assertEqual(original, self.cluster.target)
        self.assertEqual(siblings, self.cluster.siblings)
        self.assertEqual(self.cluster.writes, 1)
        self.assertNotIn("do-not-print-this", self.output + self.receipt_path.read_text())
        self.assertNotIn("secretKeyRef", self.output + self.receipt_path.read_text())

    def test_rollback_reconstitutes_exact_prior_spec_with_fresh_cas(self):
        before = copy.deepcopy(self.cluster.target["spec"])
        receipt = self.deploy()
        self.cluster.target["metadata"]["resourceVersion"] = "99"  # rollout status updates are normal
        baseline = worker.snapshot(self.cluster)[1]
        with contextlib.redirect_stdout(io.StringIO()):
            reverse = worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        worker.verify(reverse, self.cluster)
        self.assertEqual(self.cluster.writes, 2)
        self.assertEqual(self.cluster.target["spec"], before)

    def test_target_spec_drift_refuses_before_write(self):
        self.cluster.target["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] = 30
        with self.assertRaisesRegex(ValueError, "drift"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_concurrent_write_is_atomically_rejected_by_cas(self):
        self.cluster.drift_on_patch = True
        with self.assertRaisesRegex(ValueError, "API conflict"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_admission_dry_run_cannot_change_runtime_configuration(self):
        self.cluster.admission_mutates = True
        with self.assertRaisesRegex(ValueError, "admission dry-run"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_sibling_drift_immediately_before_patch_refuses(self):
        self.cluster.drift_on_consumer_read = self.cluster.consumer_reads + 3
        with self.assertRaisesRegex(ValueError, "consumer drift"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_unaccounted_shared_consumers_refuse(self):
        self.cluster.siblings.append(deployment("new-repair-consumer"))
        with self.assertRaisesRegex(ValueError, "drift"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_wrong_namespace_name_kind_strategy_container_and_mutable_image_refuse(self):
        for mutate in (
            lambda o: o["metadata"].update(namespace="dev-omi-backend"),
            lambda o: o["metadata"].update(name="wrong"),
            lambda o: o.update(kind="StatefulSet"),
            # RollingUpdate without an explicit zero maxSurge (Kubernetes defaults it to 25%).
            lambda o: o["spec"]["strategy"].update(type="RollingUpdate"),
            lambda o: o["spec"].update(strategy={"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": "25%"}}),
            lambda o: o["spec"].update(strategy={"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}}),
            lambda o: o["spec"].update(strategy={"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"}}),
            lambda o: o["spec"].update(strategy={}),
            lambda o: o["spec"]["template"]["spec"]["containers"].append(copy.deepcopy(o["spec"]["template"]["spec"]["containers"][0])),
            lambda o: o["spec"]["template"]["spec"]["containers"][0].update(name="not-worker"),
            lambda o: o["spec"]["template"]["spec"]["containers"][0].update(image=worker.REPOSITORY + ":main"),
        ):
            with self.subTest(mutate=mutate):
                self.cluster.target = deployment()
                mutate(self.cluster.target)
                with self.assertRaises(ValueError):
                    self.deploy()
                self.assertEqual(self.cluster.writes, 0)

    def test_surge_capable_strategy_refuses_on_its_own_gate(self):
        # The baseline is captured after the mutation, so only the strategy gate can refuse.
        for strategy in (
            {"type": "RollingUpdate"},
            {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": "25%"}},
            {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}},
            {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"}},
            {},
        ):
            with self.subTest(strategy=strategy):
                self.cluster = Cluster()
                self.cluster.target["spec"]["strategy"] = strategy
                with self.assertRaisesRegex(ValueError, "worker must roll without surge GPUs"):
                    self.baseline = worker.snapshot(self.cluster)[1]
                    self.deploy()
                self.assertEqual(self.cluster.writes, 0)

    def test_no_surge_rolling_update_is_admitted_and_preserved(self):
        # SCA-3274: the worker rolls in place with maxSurge 0 so no GPU node empties mid-roll.
        for rolling in ({"maxSurge": 0, "maxUnavailable": "25%"}, {"maxSurge": "0%", "maxUnavailable": 1}):
            with self.subTest(rolling=rolling):
                self.cluster = Cluster()
                self.cluster.target["spec"]["strategy"] = {"type": "RollingUpdate", "rollingUpdate": dict(rolling)}
                self.baseline = worker.snapshot(self.cluster)[1]
                original = copy.deepcopy(self.cluster.target)
                receipt = self.deploy()
                worker.verify(receipt, self.cluster)
                self.assertEqual(self.cluster.writes, 1)
                # Only the worker image moved; the strategy and every other field are as admitted.
                self.cluster.target["spec"]["template"]["spec"]["containers"][0]["image"] = OLD
                self.assertEqual(original, self.cluster.target)

    def test_invalid_candidate_and_already_serving_refuse(self):
        for image in (OLD, worker.REPOSITORY + ":latest", "gcr.io/other@sha256:" + "2" * 64):
            with self.subTest(image=image), self.assertRaises(ValueError):
                worker.deploy(self.baseline, image, self.receipt_path, self.cluster)
        self.assertEqual(self.cluster.writes, 0)

    def test_active_t4_and_required_companion_cannot_be_silently_left_old(self):
        self.cluster.siblings[-1]["spec"]["replicas"] = 1
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "active T4"):
            self.deploy()
        self.cluster.siblings[-1]["spec"]["replicas"] = 0
        self.cluster.target["metadata"]["annotations"] = {"omi.ai/required-companion-deployment": "record-seal-worker"}
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "required companion"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_verify_and_rollback_fail_on_runtime_or_sibling_drift(self):
        receipt = self.deploy()
        self.cluster.target["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] = '{"changed":1}'
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.deploy({"target": receipt["after"], "consumers": receipt["consumers"]}, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)

    def test_rollback_refuses_forged_image_baseline_and_prior_spec(self):
        receipt = self.deploy()
        baseline = worker.snapshot(self.cluster)[1]
        for changed_receipt, image, changed_baseline in (
            (receipt, NEW, baseline),
            ({**receipt, "before": {**receipt["before"], "spec_sha256": "forged"}}, OLD, baseline),
            (receipt, OLD, {**baseline, "consumers": []}),
        ):
            with self.subTest(image=image), self.assertRaises(ValueError):
                worker.deploy(changed_baseline, image, self.receipt_path, self.cluster, rollback_receipt=changed_receipt)
        self.assertEqual(self.cluster.writes, 1)

    def test_rollback_uses_the_same_dry_run_and_cas_guards(self):
        receipt = self.deploy()
        baseline = worker.snapshot(self.cluster)[1]
        self.cluster.admission_mutates = True
        with self.assertRaisesRegex(ValueError, "dry-run"), contextlib.redirect_stdout(io.StringIO()):
            worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        self.cluster.admission_mutates = False
        self.cluster.drift_on_patch = True
        with self.assertRaisesRegex(ValueError, "API conflict"), contextlib.redirect_stdout(io.StringIO()):
            worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        self.assertEqual(self.cluster.writes, 1)

    def test_cronjob_job_and_init_container_bindings_are_accounted_for(self):
        obj = deployment("record-seal-repair")
        obj["kind"] = "CronJob"
        obj["spec"] = {"suspend": True, "jobTemplate": {"spec": {"template": obj["spec"]["template"]}}}
        pod = worker.pod_spec(obj)
        pod["initContainers"] = [{"name": "init", "image": NEW}]
        bindings = worker.consumers([obj])
        self.assertEqual(len(bindings), 2)
        self.assertEqual({b["field"] for b in bindings}, {"containers", "initContainers"})
        obj["kind"] = "Job"
        obj["spec"] = obj["spec"]["jobTemplate"]["spec"]
        self.assertEqual(len(worker.consumers([obj])), 2)


    # --- HPA replica changes and CronJob Job turnover (SCA-2944) ---------------------------

    def add_sweeper(self, jobs=("record-seal-sweeper-1", "record-seal-sweeper-2")):
        sweeper = cronjob("record-seal-sweeper")
        self.cluster.siblings.append(sweeper)
        for name in jobs:
            self.cluster.siblings.append(job(name, sweeper))
        self.baseline = worker.snapshot(self.cluster)[1]
        return sweeper

    def turn_over_jobs(self, sweeper, created, deleted):
        names = [s["metadata"]["name"] for s in self.cluster.siblings]
        self.assertIn(deleted, names)
        self.assertNotIn(created, names)
        self.cluster.siblings = [s for s in self.cluster.siblings if s["metadata"]["name"] != deleted]
        self.cluster.siblings.append(job(created, sweeper))

    def test_hpa_replica_change_before_deploy_is_tolerated_and_preserved(self):
        self.cluster.target["spec"]["replicas"] = 7
        receipt = self.deploy()
        self.assertEqual(self.cluster.writes, 1)
        self.assertEqual(self.cluster.target["spec"]["replicas"], 7)
        worker.verify(receipt, self.cluster)

    def test_verify_and_rollback_tolerate_hpa_replica_changes_on_target_and_siblings(self):
        receipt = self.deploy()
        self.cluster.target["spec"]["replicas"] = 14
        self.cluster.siblings[0]["spec"]["replicas"] = 3  # record-seal-worker has its own HPA
        worker.verify(receipt, self.cluster)
        self.cluster.target["spec"]["replicas"] = 16
        baseline = worker.snapshot(self.cluster)[1]
        with contextlib.redirect_stdout(io.StringIO()):
            reverse = worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        self.cluster.target["spec"]["replicas"] = 4
        worker.verify(reverse, self.cluster)
        self.assertEqual(self.cluster.writes, 2)
        self.assertEqual(self.cluster.target["spec"]["template"]["spec"]["containers"][0]["image"], OLD)

    def test_cronjob_job_created_or_deleted_between_reads_is_tolerated(self):
        sweeper = self.add_sweeper()
        self.turn_over_jobs(sweeper, "record-seal-sweeper-3", "record-seal-sweeper-1")
        receipt = self.deploy()
        self.turn_over_jobs(sweeper, "record-seal-sweeper-4", "record-seal-sweeper-2")
        worker.verify(receipt, self.cluster)
        self.turn_over_jobs(sweeper, "record-seal-sweeper-5", "record-seal-sweeper-3")
        baseline = worker.snapshot(self.cluster)[1]
        with contextlib.redirect_stdout(io.StringIO()):
            reverse = worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        self.turn_over_jobs(sweeper, "record-seal-sweeper-6", "record-seal-sweeper-4")
        worker.verify(reverse, self.cluster)
        self.assertEqual(self.cluster.writes, 2)

    def test_target_image_change_after_roll_fails_closed(self):
        receipt = self.deploy()
        self.cluster.target["spec"]["template"]["spec"]["containers"][0]["image"] = THIRD
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_sibling_or_cronjob_image_change_fails_closed(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        worker.pod_spec(sweeper)["containers"][0]["image"] = THIRD
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        worker.pod_spec(sweeper)["containers"][0]["image"] = OLD
        worker.verify(receipt, self.cluster)
        worker.pod_spec(self.cluster.siblings[0])["containers"][0]["image"] = THIRD
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_uid_change_fails_closed_for_target_and_siblings(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        self.cluster.target["metadata"]["uid"] = "recreated-uid"
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        self.cluster.target["metadata"]["uid"] = worker.TARGET + "-uid"
        sweeper["metadata"]["uid"] = "recreated-cronjob"
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_unrelated_spec_change_still_fails_closed(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        for mutate, restore in (
            (lambda: self.cluster.target["spec"].update(minReadySeconds=5),
             lambda: self.cluster.target["spec"].pop("minReadySeconds")),
            (lambda: self.cluster.target["spec"]["template"]["spec"]["nodeSelector"].update(pool="cpu"),
             lambda: self.cluster.target["spec"]["template"]["spec"]["nodeSelector"].update(pool="gpu")),
            (lambda: sweeper["spec"].update(schedule="*/5 * * * *"),
             lambda: sweeper["spec"].update(schedule="0 * * * *")),
            (lambda: self.cluster.siblings[0]["spec"]["template"]["spec"].update(serviceAccountName="x"),
             lambda: self.cluster.siblings[0]["spec"]["template"]["spec"].update(serviceAccountName="existing-worker")),
        ):
            mutate()
            with self.assertRaisesRegex(ValueError, "drift"):
                worker.verify(receipt, self.cluster)
            restore()
        worker.verify(receipt, self.cluster)

    def test_jobs_without_a_listed_cronjob_controller_stay_tracked(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        self.cluster.siblings.append(job("manual-repair"))  # standalone Job using the worker image
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        self.cluster.siblings.pop()
        foreign = cronjob("not-listed")
        self.cluster.siblings.append(job("orphaned", foreign))  # owner CronJob absent from the namespace read
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        self.cluster.siblings.pop()
        bad = job("record-seal-sweeper-9", sweeper)
        worker.pod_spec(bad)["containers"][0]["image"] = worker.REPOSITORY + ":latest"
        self.cluster.siblings.append(bad)  # owned Jobs are still image-validated
        with self.assertRaisesRegex(ValueError, "mutable"):
            worker.verify(receipt, self.cluster)

    def test_t4_fallback_activating_on_old_image_after_roll_fails_closed(self):
        receipt = self.deploy()
        self.cluster.siblings[-1]["spec"]["replicas"] = 1
        with self.assertRaisesRegex(ValueError, "drift|active T4"):
            worker.verify(receipt, self.cluster)

    def test_t4_activated_between_early_check_and_final_reread_refuses_before_write(self):
        # Reads in deploy(): snapshot consumers (1), early T4 check (2), final pre-write reread (3).
        start = self.cluster.consumer_reads
        original = Cluster.__call__

        def activate_t4(cluster, *args):
            if args[0] == "get" and args[1] != "deployment" and cluster.consumer_reads == start + 2:
                cluster.siblings[-1]["spec"]["replicas"] = 1  # operator scales T4 on the old image
            return original(cluster, *args)

        self.cluster.__class__ = type("T4Cluster", (Cluster,), {"__call__": activate_t4})
        with self.assertRaisesRegex(ValueError, "consumer drift"):  # T4 replicas are bound
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_t4_replica_count_stays_bound(self):
        receipt = self.deploy()
        self.cluster.siblings[-1]["spec"]["replicas"] = 1
        worker.pod_spec(self.cluster.siblings[-1])["containers"][0]["image"] = NEW
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_active_t4_init_container_on_old_image_refuses(self):
        t4 = self.cluster.siblings[-1]
        t4["spec"]["replicas"] = 1
        worker.pod_spec(t4)["containers"][0]["image"] = NEW
        worker.pod_spec(t4)["initContainers"] = [{"name": "warm", "image": OLD}]
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "active T4"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_unlisted_deployment_and_statefulset_replicas_stay_bound(self):
        other = deployment("other-consumer")
        stateful = deployment("stateful-consumer")
        stateful["kind"] = "StatefulSet"
        self.cluster.siblings += [other, stateful]
        self.baseline = worker.snapshot(self.cluster)[1]
        receipt = self.deploy()
        for obj in (other, stateful):
            obj["spec"]["replicas"] += 1
            with self.assertRaisesRegex(ValueError, "drift"):
                worker.verify(receipt, self.cluster)
            obj["spec"]["replicas"] -= 1

    def test_owned_job_on_a_different_digest_than_its_cronjob_stays_bound(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        stale = job("record-seal-sweeper-7", sweeper)
        worker.pod_spec(stale)["containers"][0]["image"] = THIRD
        self.cluster.siblings.append(stale)
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_uidless_cronjob_does_not_adopt_uidless_owner_references(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        orphan = job("ghost-1", sweeper)
        orphan["metadata"]["ownerReferences"][0].pop("uid")
        self.cluster.siblings += [orphan]
        self.assertFalse(worker.cronjob_history(orphan, {None: sweeper}))
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_require_t4_serves_is_a_direct_guard(self):
        t4 = copy.deepcopy(self.cluster.siblings[-1])
        worker.require_t4_serves([t4], NEW)  # inactive T4 is ignored
        t4["spec"]["replicas"] = 2
        with self.assertRaisesRegex(ValueError, "active T4"):
            worker.require_t4_serves([t4], NEW)
        worker.pod_spec(t4)["containers"][0]["image"] = NEW
        worker.require_t4_serves([t4], NEW)
        worker.pod_spec(t4)["initContainers"] = [{"name": "warm", "image": OLD}]
        with self.assertRaisesRegex(ValueError, "active T4"):
            worker.require_t4_serves([t4], NEW)

    def test_replica_exclusion_requires_a_live_hpa_per_listed_deployment(self):
        for mutate in (
            lambda c: c.hpas.pop(0),
            lambda c: c.hpas[0]["spec"]["scaleTargetRef"].update(name="elsewhere"),
            lambda c: c.hpas[1]["spec"].update(minReplicas=0),
            lambda c: c.hpas.append(hpa(worker.TARGET)),
        ):
            with self.subTest(mutate=mutate):
                self.cluster = Cluster()
                mutate(self.cluster)
                with self.assertRaisesRegex(ValueError, "HPA"):
                    worker.snapshot(self.cluster)

    def test_hpa_spec_or_uid_change_after_roll_fails_closed(self):
        receipt = self.deploy()
        self.cluster.hpas[0]["spec"]["maxReplicas"] = 40
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        self.cluster.hpas[0]["spec"]["maxReplicas"] = 16
        self.cluster.hpas[1]["metadata"]["uid"] = "recreated"
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_owned_job_with_independent_spec_change_stays_bound(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        for change in ({"parallelism": 3}, {"suspend": True}, {"activeDeadlineSeconds": 60}):
            with self.subTest(change=change):
                run = job("record-seal-sweeper-8", sweeper)
                run["spec"].update(change)
                self.cluster.siblings.append(run)
                with self.assertRaisesRegex(ValueError, "drift"):
                    worker.verify(receipt, self.cluster)
                self.cluster.siblings.pop()
        run = job("record-seal-sweeper-8", sweeper)
        worker.pod_spec(run)["serviceAccountName"] = "other"
        self.cluster.siblings.append(run)
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_owner_reference_on_a_non_generated_job_name_stays_bound(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        self.cluster.siblings.append(job("hand-made", sweeper))
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)

    def test_hpa_rescale_between_first_read_and_write_still_writes(self):
        self.cluster.deployment_reads = 0
        self.cluster.rescale_before_write = 11
        receipt = self.deploy()
        self.assertEqual(self.cluster.writes, 1)
        self.assertEqual(self.cluster.target["spec"]["replicas"], 11)
        self.assertEqual(self.cluster.target["spec"]["template"]["spec"]["containers"][0]["image"], NEW)
        worker.verify(receipt, self.cluster)

    def test_owned_job_with_foreign_selector_or_generated_labels_stays_bound(self):
        sweeper = self.add_sweeper()
        receipt = self.deploy()
        for mutate in (
            lambda j: j["spec"].update(selector={"matchLabels": {"app": "record-seal-sweeper"}}),
            lambda j: j["spec"]["template"]["metadata"]["labels"].update({"controller-uid": "someone-else"}),
            lambda j: j["spec"]["template"]["metadata"]["labels"].pop("job-name"),
        ):
            with self.subTest(mutate=mutate):
                run = job("record-seal-sweeper-8", sweeper)
                mutate(run)
                self.cluster.siblings.append(run)
                with self.assertRaisesRegex(ValueError, "drift"):
                    worker.verify(receipt, self.cluster)
                self.cluster.siblings.pop()

    def test_hpa_with_wrong_target_api_version_is_not_proof(self):
        self.cluster.hpas[0]["spec"]["scaleTargetRef"]["apiVersion"] = "extensions/v1beta1"
        with self.assertRaisesRegex(ValueError, "HPA"):
            worker.snapshot(self.cluster)

    def test_terminating_hpa_is_not_proof(self):
        self.cluster.hpas[1]["metadata"]["deletionTimestamp"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "HPA"):
            worker.snapshot(self.cluster)

    def test_rescale_after_the_fresh_read_still_refuses_by_cas(self):
        self.cluster.drift_on_patch = True  # resourceVersion moves after the fresh read
        with self.assertRaisesRegex(ValueError, "API conflict"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_printed_patch_is_the_patch_sent(self):
        self.cluster.deployment_reads = 0
        self.cluster.rescale_before_write = 11
        self.deploy()
        printed = json.loads(self.output.strip().splitlines()[-1])["patch"]
        self.assertIn({"op": "test", "path": "/metadata/resourceVersion", "value": "40"}, printed)

    def test_hpa_chart_tripwire_matches_listed_deployments(self):
        # If the chart renders another HPA-scaled worker-image Deployment (e.g. borrowed node pools),
        # HPA_DEPLOYMENTS must be reviewed; this test is triggered by chart changes.
        chart = Path(__file__).parents[2] / "backend/charts/batch-pipeline-worker/prod_omi_batch-pipeline-worker_values.yaml"
        values = yaml.safe_load(chart.read_text())
        self.assertFalse((values.get("borrowedNodePools") or {}).get("enabled", False))
        self.assertEqual(worker.HPA_DEPLOYMENTS, frozenset({worker.TARGET, "record-seal-worker"}))

    def test_admission_change_on_the_real_write_only_escalates(self):
        self.cluster.admission_mutates_on_write = True
        with self.assertRaisesRegex(ValueError, "stop and escalate"):
            self.deploy()

    def test_replay_2026_11_14_post_roll_drift_shape_now_verifies(self):
        # Run 43619755069 (2026-11-14): image moved, then verify refused with
        # "post-roll runtime/consumer drift". Its receipt bound two CronJobs, the T4 and
        # record-seal-worker Deployments and seven CronJob-owned Jobs; the target is HPA-scaled.
        repair, sweeper = cronjob("record-seal-repair"), cronjob("record-seal-sweeper")
        self.cluster.siblings += [repair, sweeper]
        for name in ("29910915", "29911010", "29911230", "29911260"):
            self.cluster.siblings.append(job("record-seal-repair-" + name, repair))
        for name in ("29906100", "29906820", "29911260"):
            self.cluster.siblings.append(job("record-seal-sweeper-" + name, sweeper))
        self.cluster.target["spec"]["replicas"] = 16
        self.baseline = worker.snapshot(self.cluster)[1]
        receipt = self.deploy()
        full_after = worker.digest(self.cluster.target["spec"])
        legacy_consumers = sum(o["metadata"]["name"].startswith("record-seal-") and o["kind"] == "Job" for o in self.cluster.siblings)
        # During the Recreate rollout: the HPA rescales and both CronJobs rotate history.
        self.cluster.target["spec"]["replicas"] = 12
        self.cluster.siblings = [s for s in self.cluster.siblings
                                 if s["metadata"]["name"] not in ("record-seal-repair-29910915", "record-seal-sweeper-29906100")]
        self.cluster.siblings += [job("record-seal-repair-29911290", repair), job("record-seal-sweeper-29911320", sweeper)]
        _, actual = worker.snapshot(self.cluster)
        # The pre-fix full-spec hash and Job binding set both change, which is the 11-14 refusal.
        self.assertNotEqual(worker.digest(self.cluster.target["spec"]), full_after)
        self.assertEqual(legacy_consumers, 7)
        worker.verify(receipt, self.cluster)
        self.assertEqual(actual, {"target": receipt["after"], "consumers": receipt["consumers"]})



class Recorder:
    """Wrap a fake cluster and record every API call, so dry-run can prove it never writes."""

    def __init__(self, cluster):
        self.cluster, self.calls = cluster, []

    def __call__(self, *args):
        self.calls.append(args)
        return self.cluster(*args)


def is_write(args):
    dry = [a for a in args if a == "--dry-run" or str(a).startswith("--dry-run=")]
    return args[0] != "get" and dry != ["--dry-run=server"]


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.cluster = Cluster()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.receipt_path = Path(self.tmp.name) / "dry-run.json"
        self.baseline = worker.snapshot(self.cluster)[1]
        self.before = copy.deepcopy(self.cluster.target)
        env = os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(env)))

    def dry_run(self, image):
        os.environ[worker.DRY_RUN_ENV] = "1"
        recorder = Recorder(self.cluster)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = worker.dry_run(self.baseline, image, self.receipt_path, recorder)
        self.output = output.getvalue()
        return result, recorder

    def assert_nothing_written(self, recorder):
        self.assertEqual(self.cluster.writes, 0)
        self.assertEqual(self.cluster.target, self.before)
        self.assertEqual([c for c in recorder.calls if is_write(c)], [])
        self.assertTrue(any("--dry-run=server" in c for c in recorder.calls))

    def test_prior_image_inverse_dry_run_never_writes_and_records_a_receipt(self):
        result, recorder = self.dry_run(OLD)  # the prior digest is the live image
        self.assert_nothing_written(recorder)
        saved = json.loads(self.receipt_path.read_text())
        self.assertEqual(saved, result)
        self.assertEqual(saved["mode"], "dry-run")
        self.assertTrue(saved["prior_image_admission"]["admitted"])
        self.assertTrue(saved["prior_image_admission"]["noop"])
        # The pre-forward receipt must not claim rollback admission; only the post-forward rehearsal can.
        self.assertEqual(saved["inverse_admission"], "not verified before the forward roll; rehearse with worker_rollback_receipt")
        self.assertEqual(saved["prior_image_admission"]["image"], OLD)
        self.assertIsNone(saved["forward"])
        self.assertIsNone(saved["inverse"])
        self.assertNotIn("do-not-print-this", self.output + self.receipt_path.read_text())

    def test_forward_and_inverse_dry_run_never_writes(self):
        result, recorder = self.dry_run(NEW)
        self.assert_nothing_written(recorder)
        self.assertTrue(result["forward"]["admitted"])
        self.assertEqual(result["forward"]["after"]["image"], NEW)
        self.assertTrue(result["prior_image_admission"]["admitted"])
        self.assertTrue(result["forward"]["inverse_restores_before"])
        self.assertEqual(result["forward"]["would_write_receipt"]["before"], self.baseline["target"])
        # The inverse is built from the server's admitted preview object, not a local copy.
        self.assertIn("rebuilds", result["forward"]["inverse_patch_note"])
        inverse = result["forward"]["inverse_patch"]
        self.assertEqual([op["value"] for op in inverse[2:]], [NEW, OLD])
        self.assertEqual(inverse[0]["value"], self.baseline["target"]["uid"])

    def test_forward_inverse_check_uses_the_server_preview(self):
        # A preview whose post-roll object would not restore the live identity must refuse, which a check
        # on a local copy of the live object could never detect.
        original = worker.target_state
        calls = []

        def target_state(obj):
            state, index = original(obj)
            if obj.get("_preview"):
                calls.append(1)
                if len(calls) > 1:  # the post-roll object, after the inverse image is restored
                    state = dict(state, spec_sha256="0" * 64)
            return state, index

        cluster_call = Cluster.__call__

        def mark(cluster, *args):
            out = cluster_call(cluster, *args)
            if args[0] == "patch" and "--dry-run=server" in args and json.loads(args[args.index("-p") + 1])[3]["value"] == NEW:
                out = copy.deepcopy(out)
                out["_preview"] = True
            return out

        self.cluster.__class__ = type("PreviewCluster", (Cluster,), {"__call__": mark})
        with mock.patch.object(worker, "target_state", target_state):
            with self.assertRaisesRegex(ValueError, "inverse of the forward patch does not restore"):
                self.dry_run(NEW)
        self.assertEqual(self.cluster.writes, 0)

    def test_dry_run_still_refuses_drift_admission_change_and_t4(self):
        self.cluster.target["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] = 30
        with self.assertRaisesRegex(ValueError, "drift"):
            self.dry_run(NEW)
        self.cluster = Cluster()
        self.baseline = worker.snapshot(self.cluster)[1]
        self.cluster.admission_mutates = True
        with self.assertRaisesRegex(ValueError, "admission dry-run"):
            self.dry_run(NEW)
        self.cluster = Cluster()
        self.cluster.siblings[-1]["spec"]["replicas"] = 1
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "active T4"):
            self.dry_run(NEW)
        self.assertEqual(self.cluster.writes, 0)

    def test_mode_env_makes_every_write_path_unreachable(self):
        os.environ[worker.DRY_RUN_ENV] = "1"
        recorder = Recorder(self.cluster)
        with self.assertRaisesRegex(ValueError, "dry-run mode"), contextlib.redirect_stdout(io.StringIO()):
            worker.deploy(self.baseline, NEW, self.receipt_path, recorder)
        self.assertEqual(self.cluster.writes, 0)
        self.assertEqual([c for c in recorder.calls if is_write(c)], [])
        with self.assertRaisesRegex(ValueError, "dry-run mode"):
            worker.guarded(recorder)("patch", "deployment", worker.TARGET, "--type=json", "-p", "[]", "-o", "json")
        for verb in ("apply", "replace", "create", "delete", "scale", "rollout", "annotate", "label", "set", "edit"):
            with self.subTest(verb=verb), self.assertRaisesRegex(ValueError, "dry-run mode"):
                worker.guarded(recorder)(verb, "deployment", worker.TARGET)
        self.assertEqual(self.cluster.writes, 0)

    def test_cli_refuses_deploy_when_mode_env_is_set(self):
        script = Path(worker.__file__)
        env = {**os.environ, worker.DRY_RUN_ENV: "1", "PATH": "/nonexistent"}  # no kubectl reachable
        result = subprocess.run([sys.executable, str(script), "deploy", "--baseline", "b", "--image", NEW, "--receipt", "r"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("dry-run mode", result.stderr)

    def test_receipt_bound_inverse_dry_run_after_a_forward_roll_sends_the_real_rollback_cas(self):
        with contextlib.redirect_stdout(io.StringIO()):
            receipt = worker.deploy(self.baseline, NEW, Path(self.tmp.name) / "forward.json", self.cluster)
        self.cluster.target["spec"]["replicas"] = 13  # HPA moved after the roll
        self.baseline = worker.snapshot(self.cluster)[1]
        self.before = copy.deepcopy(self.cluster.target)
        writes = self.cluster.writes
        os.environ[worker.DRY_RUN_ENV] = "1"
        recorder = Recorder(self.cluster)
        with contextlib.redirect_stdout(io.StringIO()):
            result = worker.dry_run(self.baseline, OLD, self.receipt_path, recorder, rollback_receipt=receipt)
        self.assertEqual(self.cluster.writes, writes)
        self.assertEqual(self.cluster.target, self.before)
        self.assertEqual([c for c in recorder.calls if is_write(c)], [])
        self.assertEqual(result["inverse"]["restores"], receipt["before"])
        self.assertEqual(result["inverse_admission"], "verified: server dry-run of the real rollback CAS patch")
        self.assertIn({"op": "test", "path": "/spec/template/spec/containers/0/image", "value": NEW}, result["inverse"]["patch"])
        forged = {**receipt, "before": {**receipt["before"], "spec_sha256": "forged"}}
        with self.assertRaisesRegex(ValueError, "rollback"):
            worker.dry_run(self.baseline, OLD, self.receipt_path, recorder, rollback_receipt=forged)
        with self.assertRaisesRegex(ValueError, "rollback"):
            worker.dry_run(self.baseline, NEW, self.receipt_path, recorder, rollback_receipt=receipt)
        self.assertEqual(self.cluster.writes, writes)

    def test_forward_dry_run_refuses_when_the_inverse_gates_would_refuse(self):
        t4 = self.cluster.siblings[-1]
        t4["spec"]["replicas"] = 1
        worker.pod_spec(t4)["containers"][0]["image"] = NEW  # active T4 already on the candidate
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "inverse would refuse"):
            self.dry_run(NEW)
        self.cluster = Cluster()
        self.cluster.target["metadata"]["annotations"] = {"omi.ai/required-companion-deployment": "record-seal-worker"}
        worker.pod_spec(self.cluster.siblings[0])["containers"][0]["image"] = NEW
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "inverse would refuse"):
            self.dry_run(NEW)
        self.assertEqual(self.cluster.writes, 0)

    def test_dry_run_applies_the_required_companion_gate(self):
        self.cluster.target["metadata"]["annotations"] = {"omi.ai/required-companion-deployment": "record-seal-worker"}
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "required companion"):
            self.dry_run(NEW)
        self.assertEqual(self.cluster.writes, 0)

    def activate_t4_before_final_read(self):
        start = self.cluster.consumer_reads
        original = Cluster.__call__

        def activate_t4(cluster, *args):
            if args[0] == "get" and args[1] != "deployment" and cluster.consumer_reads == start + 3:
                cluster.siblings[-1]["spec"]["replicas"] = 1
            return original(cluster, *args)

        self.cluster.__class__ = type("T4Cluster", (Cluster,), {"__call__": activate_t4})

    def test_dry_run_final_read_refuses_t4_replica_drift(self):
        self.activate_t4_before_final_read()
        with self.assertRaisesRegex(ValueError, "^consumer drift$"):
            self.dry_run(NEW)
        self.assertEqual(self.cluster.writes, 0)

    def test_dry_run_rechecks_t4_on_the_final_read(self):
        # Isolate the T4 gate: let the final bindings comparison pass so only require_t4_serves can refuse.
        self.activate_t4_before_final_read()
        real_bindings = worker.bindings
        calls = []

        def bindings(items):
            calls.append(1)
            return self.baseline["consumers"] if len(calls) > 1 else real_bindings(items)

        with mock.patch.object(worker, "bindings", bindings):
            with self.assertRaisesRegex(ValueError, "active T4 fallback must already serve the candidate"):
                self.dry_run(NEW)
        self.assertEqual(self.cluster.writes, 0)

    def test_guard_allows_only_reads_and_server_dry_run_patches(self):
        os.environ[worker.DRY_RUN_ENV] = "1"
        recorder = Recorder(self.cluster)
        for verb in ("delete", "apply", "replace", "scale", "create"):
            with self.subTest(verb=verb), self.assertRaisesRegex(ValueError, "dry-run mode"):
                worker.guarded(recorder)(verb, "deployment", worker.TARGET, "--dry-run=server")
        self.assertEqual(recorder.calls, [])

    def test_transport_refuses_writes_in_dry_run_mode_before_subprocess(self):
        os.environ[worker.DRY_RUN_ENV] = "1"
        with mock.patch.object(worker.subprocess, "run") as run:
            for args in (("delete", "deployment", worker.TARGET), ("patch", "deployment", worker.TARGET, "-p", "[]"),
                         ("patch", "deployment", worker.TARGET, "--dry-run=server", "--dry-run=none")):
                with self.subTest(args=args), self.assertRaisesRegex(ValueError, "dry-run mode"):
                    worker.kubectl(*args)
        run.assert_not_called()

    def test_dry_run_through_the_real_transport_sends_no_write(self):
        # Route the real kubectl() transport into the fake cluster; every argv that reaches subprocess must
        # be a read or a single server dry-run.
        seen = []

        def fake_subprocess_run(argv, **kwargs):
            self.assertEqual(argv[:3], ["kubectl", "-n", worker.NAMESPACE])
            self.assertEqual(argv[-1], "--request-timeout=30s")
            args = tuple(argv[3:-1])
            seen.append(args)
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(self.cluster(*args)), stderr="")

        os.environ[worker.DRY_RUN_ENV] = "1"
        with mock.patch.object(worker.subprocess, "run", fake_subprocess_run), contextlib.redirect_stdout(io.StringIO()):
            worker.dry_run(self.baseline, NEW, self.receipt_path)
        self.assertTrue(seen)
        self.assertEqual([args for args in seen if is_write(args)], [])
        self.assertEqual(self.cluster.writes, 0)

    # The helper's reviewed imports; anything else (an HTTP client, a Kubernetes SDK, importlib) fails closed.
    REVIEWED_IMPORTS = {"__future__", "argparse", "copy", "hashlib", "json", "os", "pathlib", "re", "subprocess", "sys"}
    # The only os attributes the helper may use (fail closed: any process-spawn variant is outside this set).
    REVIEWED_OS_ATTRS = {"environ", "fdopen", "open", "O_WRONLY", "O_CREAT", "O_TRUNC"}

    def boundary_violations(self, source):
        import ast
        tree = ast.parse(source)
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] not in self.REVIEWED_IMPORTS]
                # An alias would hide process calls from the attribute check below.
                found += [f"import {a.name} as {a.asname}" for a in node.names
                          if a.asname and a.name.split(".")[0] in ("os", "subprocess")]
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] not in self.REVIEWED_IMPORTS:
                    found.append(f"from {node.module} import")
                elif (node.module or "").split(".")[0] in ("os", "subprocess"):
                    found.append(f"from {node.module} import")
            elif isinstance(node, ast.Name) and node.id in ("__import__", "eval", "exec", "compile", "getattr", "vars",
                                                              "globals", "locals", "setattr"):
                found.append(node.id)
        # Inside kubectl(), exactly one call is allowed: the guarded subprocess.run of a kubectl argv.
        allowed = set()
        kubectl_functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "kubectl"]
        for function in kubectl_functions:
            runs = [n for n in ast.walk(function) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                    and n.value.id == "subprocess"]
            calls = [n for n in ast.walk(function) if isinstance(n, ast.Call) and n.func in runs]
            ok = (len(runs) == 1 and runs[0].attr == "run" and len(calls) == 1 and calls[0].args
                  and isinstance(calls[0].args[0], ast.List) and isinstance(calls[0].args[0].elts[0], ast.Constant)
                  and calls[0].args[0].elts[0].value == "kubectl")
            first = function.body[0] if function.body else None
            guard = (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
                     and getattr(first.value.func, "id", None) == "require_dry_run_allows")
            if ok and guard:
                allowed.add(id(runs[0]))
            else:
                found.append("kubectl() must first call require_dry_run_allows, then exactly one subprocess.run(['kubectl', ...])")
        if len(kubectl_functions) != 1:
            found.append("exactly one kubectl() definition")
        parents = {id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Name) and node.id in ("os", "subprocess")):
                continue
            parent = parents.get(id(node))
            # The module may only be used as `module.attr`; a bare reference could re-bind it out of sight.
            if not (isinstance(parent, ast.Attribute) and parent.value is node):
                found.append(f"bare {node.id}")
            elif node.id == "subprocess" and parent.attr != "TimeoutExpired" and id(parent) not in allowed:
                found.append(f"subprocess.{parent.attr}")
            elif node.id == "os" and parent.attr not in self.REVIEWED_OS_ATTRS:
                found.append(f"os.{parent.attr}")
        return found

    def test_kubectl_is_the_only_process_or_network_boundary(self):
        self.assertEqual(self.boundary_violations(Path(worker.__file__).read_text()), [])

    def test_boundary_check_rejects_extra_calls_inside_kubectl(self):
        source = Path(worker.__file__).read_text()
        anchor = "    require_dry_run_allows(args)\n    result = subprocess.run("
        self.assertEqual(source.count(anchor), 1)
        for extra in ("    subprocess.Popen(['kubectl', 'delete'])\n", "    subprocess.run(['kubectl', 'delete'])\n"):
            with self.subTest(extra=extra):
                bad = source.replace(anchor, anchor.replace("    result", extra + "    result"))
                self.assertTrue(self.boundary_violations(bad))
        self.assertTrue(self.boundary_violations(source.replace("    require_dry_run_allows(args)\n    result", "    result")))

    def test_boundary_check_rejects_alternate_clients(self):
        source = Path(worker.__file__).read_text()
        for extra in ("import urllib3\n", "from subprocess import run\n", "import subprocess as sp\n",
                      "from os import system\n", "import os as o\n",
                      "transport = subprocess\ndef w():\n    transport.run(['kubectl'])\n",
                      "def w():\n    getattr(subprocess, 'run')(['kubectl'])\n", "def w(m=os):\n    m.system('x')\n",
                      "def w():\n    os.spawnvp(0, 'x', ['x'])\n", "def w():\n    os.execle('x', 'x', {})\n", "from kubernetes import client\n", "import importlib\n",
                      "def other():\n    return subprocess.run(['kubectl'])\n", "subprocess.Popen(['x'])\n",
                      "def f():\n    os.system('x')\n", "def f():\n    return __import__('socket')\n"):
            with self.subTest(extra=extra):
                self.assertTrue(self.boundary_violations(source + "\n" + extra), extra)

    def test_guard_refuses_conflicting_or_duplicate_dry_run_flags(self):
        os.environ[worker.DRY_RUN_ENV] = "1"
        recorder = Recorder(self.cluster)
        for flags in (("--dry-run=server", "--dry-run=none"), ("--dry-run=none", "--dry-run=server"),
                      ("--dry-run=server", "--dry-run=server"), ("--dry-run", "--dry-run=server"),
                      ("--dry-run=client",), ()):
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, "dry-run mode"):
                worker.guarded(recorder)("patch", "deployment", worker.TARGET, "--type=json", "-p", "[]", *flags)
            self.assertTrue(is_write(("patch", "deployment", *flags)), flags)
        self.assertEqual(recorder.calls, [])

    def test_dry_run_command_requires_the_mode_env(self):
        with self.assertRaisesRegex(ValueError, "dry-run"):
            worker.require_dry_run_env()
        os.environ[worker.DRY_RUN_ENV] = "1"
        worker.require_dry_run_env()

    def test_dry_run_refuses_without_the_mode_env(self):
        os.environ.pop(worker.DRY_RUN_ENV, None)
        recorder = Recorder(self.cluster)
        with self.assertRaisesRegex(ValueError, "dry-run command requires"):
            worker.dry_run(self.baseline, NEW, self.receipt_path, recorder)
        self.assertEqual(recorder.calls, [])
        baseline = Path(self.tmp.name) / "baseline.json"
        baseline.write_text(json.dumps(self.baseline))
        env = {k: v for k, v in os.environ.items() if k != worker.DRY_RUN_ENV}
        result = subprocess.run([sys.executable, worker.__file__, "dry-run", "--baseline", str(baseline), "--image", NEW,
                                 "--receipt", str(self.receipt_path)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("dry-run command requires", result.stderr)

    def test_any_value_of_the_mode_env_guards_writes(self):
        for value in ("true", "0", ""):
            with self.subTest(value=value):
                os.environ[worker.DRY_RUN_ENV] = value
                with self.assertRaisesRegex(ValueError, "dry-run mode"):
                    worker.deploy(self.baseline, NEW, self.receipt_path, self.cluster)
                with self.assertRaisesRegex(ValueError, "dry-run mode"):
                    worker.guarded(self.cluster)("delete", "deployment", worker.TARGET)
                with self.assertRaisesRegex(ValueError, "dry-run"):
                    worker.require_dry_run_env()
        self.assertEqual(self.cluster.writes, 0)


def worker_env_name():
    return worker.DRY_RUN_ENV


class WorkflowTests(unittest.TestCase):
    """Integration tripwires complement the behavioral API tests; no cloud approval simulation."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(Path(__file__).parents[1].joinpath("workflows/gcp_diarizer.yml").read_text())
        cls.steps = cls.workflow["jobs"]["deploy"]["steps"]

    def step(self, name):
        return next(s for s in self.steps if s.get("name") == name)

    def test_default_helm_path_and_success_only_writer_keep_existing_controls(self):
        helm = self.step("Deploy Diarizer to GKE cluster using Helm")
        writer = self.step("Deploy worker image preserving live runtime")
        self.assertEqual(helm["if"], "inputs.preserve_live_worker != true && inputs.worker_dry_run != true")
        self.assertEqual(writer["if"], "inputs.preserve_live_worker == true && inputs.worker_dry_run != true")
        self.assertIn('helm -n "$DEPLOY_NAMESPACE" upgrade --install', helm["run"])
        self.assertIn("environment", self.workflow["jobs"]["deploy"])
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])
        self.assertIn("'prod-train'", self.workflow["concurrency"]["group"])
        names = [s.get("name") for s in self.steps]
        for gate in ("Select merged production source and image tag", "Verify serving Firestore indexes", "Verify promoted worker digest"):
            self.assertLess(names.index(gate), names.index(writer["name"]))
        # No always(), continue-on-error, or second job can route around a failed gate.
        self.assertNotIn("continue-on-error", writer)
        self.assertEqual(list(self.workflow["jobs"]), ["deploy"])
        immutable = self.step("Checkout immutable worker image-only control")
        self.assertEqual(immutable["with"]["ref"], "${{ github.workflow_sha }}")
        self.assertEqual(immutable["with"]["sparse-checkout"], "/.github/scripts/worker_image_only.py")
        self.assertFalse(immutable["with"]["sparse-checkout-cone-mode"])
        self.assertNotIn(".github/scripts", self.step("Checkout immutable Firestore gate controls")["with"]["sparse-checkout"])
        self.assertIn("--rollback-receipt", writer["run"])

    def test_input_validation_executes_and_refuses_wrong_scope(self):
        step = self.step("Validate Environment Input")
        for environment, service, preserve, baseline, expected in (
            ("prod", "batch-pipeline-worker", "true", "{}", 0),
            ("development", "batch-pipeline-worker", "true", "{}", 1),
            ("prod", "diarizer", "true", "{}", 1),
            ("prod", "batch-pipeline-worker", "true", "", 1),
            ("prod", "diarizer", "false", "", 0),
            ("development", "diarizer", "false", "{}", 1),
        ):
            script = step["run"].replace("${{ github.event.inputs.environment }}", environment).replace("${{ inputs.environment }}", environment)
            with self.subTest(environment=environment, service=service, preserve=preserve):
                result = subprocess.run(
                    ["bash", "-e", "-c", script],
                    env={"SERVICE": service, "PRESERVE_LIVE": preserve, "LIVE_BASELINE": baseline, "ROLLBACK_RECEIPT": ""},
                    capture_output=True,
                )
                self.assertEqual(result.returncode, expected)

    def test_failed_source_ancestry_or_invalid_ref_cannot_reach_writer(self):
        script = self.step("Select merged production source and image tag")["run"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git = root / "git"
            git.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == merge-base ]]; then exit 1; fi\n'
                'if [[ "$1" == rev-parse ]]; then echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi\n'
            )
            git.chmod(0o755)
            for ref in ("unmerged-branch", "b" * 40):
                marker = root / "writer-reached"
                result = subprocess.run(
                    ["bash", "-e", "-c", script + '\nprintf writer > "$WRITE_MARKER"\n'],
                    env={
                        "PATH": str(root) + os.pathsep + os.defpath,
                        "DEPLOY_ENVIRONMENT": "prod",
                        "DEPLOY_REF": ref,
                        "PRESERVE_LIVE": "true",
                        "GITHUB_OUTPUT": str(root / "output"),
                        "WRITE_MARKER": str(marker),
                    },
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())

    def test_source_floor_refusal_precedes_forward_and_reverse_writer(self):
        script = self.step("Select merged production source and image tag")["run"]
        floor = "f3902ec5435809d95ac7c15f6be7e9f056564d3d"
        self.assertIn(f"git merge-base --is-ancestor {floor}", script)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git = root / "git"
            git.write_text(
                '#!/bin/bash\n'
                f'if [[ "$1" == merge-base && "$3" == {floor} ]]; then exit 1; fi\n'
                'if [[ "$1" == rev-parse ]]; then echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi\n'
            )
            git.chmod(0o755)
            marker = root / "writer-reached"
            result = subprocess.run(
                ["bash", "-e", "-c", script + '\nprintf writer > "$WRITE_MARKER"\n'],
                env={"PATH": str(root) + os.pathsep + os.defpath, "DEPLOY_ENVIRONMENT": "prod", "DEPLOY_REF": "b" * 40,
                     "PRESERVE_LIVE": "true", "GITHUB_OUTPUT": str(root / "output"), "WRITE_MARKER": str(marker)},
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_rollback_input_requires_same_preserve_path_and_explicit_source_digest(self):
        step = self.step("Validate Environment Input")
        script = step["run"].replace("${{ github.event.inputs.environment }}", "prod").replace("${{ inputs.environment }}", "prod")
        for preserve, ref, image, break_glass, expected in (
            ("true", "a" * 40, "sha256:" + "1" * 64, "false", 0),
            ("false", "a" * 40, "sha256:" + "1" * 64, "false", 1),
            ("true", "main", "sha256:" + "1" * 64, "false", 1),
            ("true", "a" * 40, "", "false", 1),
            ("true", "a" * 40, "sha256:" + "1" * 64, "true", 1),
        ):
            with self.subTest(preserve=preserve, ref=ref, image=image):
                result = subprocess.run(["bash", "-e", "-c", script],
                    env={"SERVICE": "batch-pipeline-worker", "PRESERVE_LIVE": preserve, "LIVE_BASELINE": "{}",
                         "ROLLBACK_RECEIPT": "{}", "SOURCE_REF": ref, "CANDIDATE_DIGEST": image, "BREAK_GLASS_LOCK": break_glass}, capture_output=True)
                self.assertEqual(result.returncode, expected)


    # --- dry-run mode (SCA-2944; David 2026-11-19) -------------------------------------------

    WRITE_MARKERS = ("worker_image_only.py deploy", "helm ", "docker push", "docker build ", "docker tag ", "docker buildx build",
                     "gsutil", "kubectl patch", "kubectl apply",
                     "kubectl replace", "kubectl scale", "kubectl delete", "kubectl create", "rollout restart",
                     "kubectl set ", "kubectl annotate", "kubectl label")

    # A gcloud segment is a read only when it is `gcloud <groups> <read verb>`, with up to three plain group
    # words and none of them a mutating verb; any other gcloud invocation counts as a write (fail closed).
    GCLOUD_READ = re.compile(r"(?:^|\s)gcloud((?:\s+[a-z][a-z0-9-]*){0,3}?)\s+"
                             r"(describe|list|configure-docker|get-credentials|print-access-token|get-value)(?=\s|$)")
    GCLOUD_MUTATING_WORDS = {"create", "delete", "update", "deploy", "cp", "rm", "mv", "add", "remove", "set", "publish",
                             "pause", "resume", "resize", "import", "export", "patch", "replace", "add-tag", "untag"}

    def gcloud_segment_reads(self, segment):
        match = self.GCLOUD_READ.search(segment)
        return bool(match) and not (set(match.group(1).split()) & self.GCLOUD_MUTATING_WORDS)

    # A kubectl segment is a read only when its verb (the first non-flag word after kubectl) is one of these.
    READ_VERBS = {"get", "describe", "auth", "config", "version", "wait", "logs", "top"}

    def kubectl_segment_reads(self, segment):
        words = segment.split()
        after = words[words.index("kubectl") + 1:]
        skip = False
        for word in after:
            if skip:
                skip = False
                continue
            if word in ("-n", "--namespace", "--context", "--request-timeout"):
                skip = True
                continue
            if word.startswith("-"):
                # Fail closed: before the verb, only reviewed global flags; an unknown one may take a value
                # that looks like a read verb (`kubectl --as get delete ...`).
                if word.split("=", 1)[0] in ("-n", "--namespace", "--context", "--request-timeout") and "=" in word:
                    continue
                return False
            if word == "rollout":
                rest = after[after.index("rollout") + 1:]
                return bool(rest) and rest[0] == "status"
            if word == "auth":
                rest = after[after.index("auth") + 1:]
                return bool(rest) and rest[0] in ("can-i", "whoami")
            return word in self.READ_VERBS
        return False

    def writes(self, run):
        if any(m in run for m in self.WRITE_MARKERS):
            return True
        # Fail closed: every kubectl invocation, split on shell separators, must be a known read.
        for segment in re.split(r"&&|\|\||;|\||\$\(|`|\n", run):
            if re.search(r"(^|\s)kubectl(\s|$)", segment) and not self.kubectl_segment_reads(segment.strip().strip('"')):
                return True
            if re.search(r"(^|\s)gcloud(\s|$)", segment) and not self.gcloud_segment_reads(segment.strip().strip('"')):
                return True
        return False

    def test_unknown_kubectl_verbs_count_as_writes(self):
        for run in ("kubectl -n x rollout undo deploy/y", "kubectl patch deploy y", "kubectl cordon n", "kubectl drain n",
                    "kubectl get pods; kubectl rollout undo deploy/x", "kubectl get deploy x && kubectl cordon n",
                    "x=$(kubectl -n ns scale deploy/y --replicas=0)", "docker build -t i .", "docker tag a b"):
            self.assertTrue(self.writes(run), run)
        for run in ("kubectl -n x get deploy y -o json", "kubectl -n x rollout status deploy/y --timeout=1s",
                    "kubectl auth can-i patch deploy"):
            self.assertFalse(self.writes(run), run)
        self.assertTrue(self.writes("kubectl auth reconcile -f rbac.yaml"))
        for run in ("kubectl --as get delete deployment/x", "kubectl --as=get delete deployment/x",
                    "kubectl -s get delete deployment/x", "kubectl --kubeconfig get patch deploy x"):
            self.assertTrue(self.writes(run), run)

    def test_unknown_gcloud_verbs_count_as_writes(self):
        for run in ("gcloud dns record-sets create x", "gcloud pubsub topics publish t --message m",
                    "x=$(gcloud scheduler jobs pause j)", "gcloud storage cp a gs://b"):
            self.assertTrue(self.writes(run), run)
        for run in ("gcloud auth configure-docker", "image_digest=\"$(gcloud container images describe \"$image\" --format='value(x)')\"",
                    "gcloud run services list --region r"):
            self.assertFalse(self.writes(run), run)

    # One argument: a bare word, an env expansion, or a double-quoted string of literals and env
    # expansions. No shell separators, pipes, command substitution or backticks anywhere.
    _ARG = r'(?:(?:[^;&|`$()<>\\\'"\s]|\$\{?[A-Z_]+\}?)+|"(?:[^"`$\\;&|()]|\$\{?[A-Z_]+\}?)*")'
    DRY_RUN_STEP_LINE = re.compile(
        r"^(?:set -euo pipefail|umask 077|fi|\{|\}(?: >> \"\$GITHUB_STEP_SUMMARY\")?|rollback_args=\(\)"
        r"|rollback_args=\(--rollback-receipt " + _ARG + r"\)"
        r"|if \[\[ -n " + _ARG + r" \]\]; then"
        r"|echo " + _ARG + r" > " + _ARG
        + r"|echo '[^']*'"
        r"|cat " + _ARG
        + r"|python3 \.github/worker-workflow/\.github/scripts/worker_image_only\.py dry-run \\"
        r"|\"\$\{rollback_args\[@\]\}\" \\"
        r"|--[a-z-]+ " + _ARG + r"(?: \\| \| tee " + _ARG + r")"
        r")$")

    def test_dry_run_step_allowlist_rejects_chained_commands(self):
        for line in ("echo x; python3 evil.py", "cat a && python3 evil.py", "--receipt r | sh", "echo $(python3 evil.py)",
                     "echo `id`"):
            self.assertIsNone(self.DRY_RUN_STEP_LINE.match(line), line)

    def test_dry_run_step_runs_only_allowlisted_commands(self):
        body = self.step("Dry-run worker image preserving live runtime")["run"]
        allowed = self.DRY_RUN_STEP_LINE
        for line in (l.strip() for l in body.splitlines()):
            if line:
                self.assertRegex(line, allowed)
        self.assertFalse(self.writes(body))

    # Reviewed uses: actions, pinned with their exact ref, that read, authenticate or report only; any other
    # uses: step (or a ref change) must exclude the mode.
    READ_ONLY_ACTIONS = {
        "actions/checkout@v7",
        "./.github/firestore-workflow/.github/actions/firestore-readiness",
        "google-github-actions/auth@v3",
        "google-github-actions/setup-gcloud@v3",
        "google-github-actions/get-gke-credentials@v3",
        "BasedHardware/omi/.github/actions/deployment-summary@979b573718fd74b31edab3530adf2ed6082622dc",
        "BasedHardware/omi/.github/actions/deployment-notifier@979b573718fd74b31edab3530adf2ed6082622dc",
    }

    EXCLUSION = "inputs.worker_dry_run != true"

    @classmethod
    def excludes_dry_run(cls, condition):
        """True only when the step condition is the exclusion itself or `<guard> && <exclusion>` with no
        top-level `||` in the guard, so it is provably false when worker_dry_run is true."""
        condition = str(condition or "").strip()
        if condition == cls.EXCLUSION:
            return True
        suffix = " && " + cls.EXCLUSION
        if not condition.endswith(suffix) or "${{" in condition:
            return False
        guard, depth = condition[: -len(suffix)], 0
        for i, char in enumerate(guard):
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth < 0 or (depth == 0 and guard.startswith("||", i)):
                return False
        return depth == 0

    # Every run: step, in any job, that is NOT excluded from dry-run mode, pinned by position, name and the
    # sha256 of its exact script. A new or moved step, or any edit to one of these scripts, fails here until it
    # is reviewed for writes (fail closed), whatever it calls.
    DRY_RUN_REACHABLE_RUN_STEPS = {
        ("deploy", 0, "Validate Environment Input"): "acfe38168b5679eccd7f1529ea4a79de772ede5a255ae5eabaf22c9ab1b8bd6a",
        ("deploy", 1, "Delete huge unnecessary tools folder"): "5a5faacb04df5aab268eb9209ca091013f37c875222610c5a0ddd92bbd270e8a",
        ("deploy", 3, "Select merged production source and image tag"): "22f8a15c2be33be8006fc5a2a8d85f4365193ad0d5f53bcd858cb7567dae70a5",
        ("deploy", 7, "Resolve deployment target"): "70e03ebe8dfbbf768522c6bc295b2c93c160c8e9346d29e3946a3afe55df14b5",
        ("deploy", 11, None): "b887a196f21fac03886c7dfbfae52c6b842028be839d6f96d5f07d74ba87c79c",  # gcloud auth configure-docker
        ("deploy", 13, "Verify promoted worker digest"): "cdc8a53e12e5dc8956abc88a2c11185c6a908728d7bb8a8965d018a6d3d536d1",
        ("deploy", 16, "Dry-run worker image preserving live runtime"): "344ade981770f2dbfb00d02bca7c30a8cf24000b144de5410256f0ac44f5a40e",
    }

    @staticmethod
    def step_digest(step):
        # Everything that shapes what the step executes: its script, env, shell and working directory.
        fields = {k: step.get(k) for k in ("run", "env", "shell", "working-directory", "continue-on-error", "if",
                                            "timeout-minutes", "id")}
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    # Workflow- and job-level execution context (env, defaults, permissions, container, environment) that
    # applies to every dry-run-reachable step; any edit fails here until reviewed.
    DRY_RUN_CONTEXT_DIGEST = "8882f0924ea82e37d94e3cb2b7e9f68a6bb37272f3d393b13b91b89a32f7f591"

    def context_digest(self):
        context = {
            "workflow": {k: self.workflow.get(k) for k in ("env", "defaults", "permissions", "concurrency")},
            "jobs": {name: {k: job.get(k) for k in ("env", "defaults", "permissions", "container", "services",
                                                      "environment", "runs-on", "if", "uses", "concurrency",
                                                      "strategy", "continue-on-error", "needs", "timeout-minutes")}
                     for name, job in self.workflow["jobs"].items()},
        }
        return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()

    def test_no_dry_run_reachable_step_continues_on_error(self):
        # A gate that continues on error would let a refused dispatch reach the dry-run step.
        for job in self.workflow["jobs"].values():
            self.assertNotIn("continue-on-error", job)
            for step in job.get("steps", []):
                if not self.excludes_dry_run(step.get("if")):
                    self.assertNotIn("continue-on-error", step, step.get("name") or step.get("uses"))

    # Every uses: step reachable in dry-run mode, pinned by position and the sha256 of its uses, with, env, if
    # and id, so an input edit (a checkout ref, credentials target) fails here until reviewed.
    DRY_RUN_REACHABLE_USES_STEPS = {
        ("deploy", 2, "actions/checkout@v7"): "4fb614bb7e46760136a1991dd31d5e0934afebee07489e943bb30fa4bb1a189f",
        ("deploy", 4, "actions/checkout@v7"): "283f9e569234e2552922cc61ee534f04186e382ef036b83d200b7cd66723c841",
        ("deploy", 5, "actions/checkout@v7"): "2ca758dd5cfcfcf1b84411b8cc51d64b964159ef2cb7ad2d53888b9b96121769",
        ("deploy", 6, "./.github/firestore-workflow/.github/actions/firestore-readiness"): "0d1f2c04c68ed64fe3aa9f9ad52cdf069fcb263c393cfe52480db951d2a1a6a0",
        ("deploy", 8, "google-github-actions/auth@v3"): "3286efbdc0d1bd5adf1bf9c3afe2c88d539cd036e9aa5a42b0edb88fd9a62f40",
        ("deploy", 9, "google-github-actions/auth@v3"): "6fc980f3f5bfc28ac2316bf7d0b0a8d3742dcb06f095984d3b19f5db6849f6b4",
        ("deploy", 10, "google-github-actions/setup-gcloud@v3"): "81788bbf5c63a19208a6c40180026073562ec37f254843f07dfeae9348f616c9",
        ("deploy", 14, "google-github-actions/get-gke-credentials@v3"): "45f3c39c6de870255d441dea6ea993c5cceb60a5c0b034d9d3563ec03f331090",
        ("deploy", 20, "BasedHardware/omi/.github/actions/deployment-summary@979b573718fd74b31edab3530adf2ed6082622dc"): "4cd14521853a508ad41a70b493185a7088ac3d4ecb72865472d638d12ede1a3c",
        ("deploy", 21, "BasedHardware/omi/.github/actions/deployment-notifier@979b573718fd74b31edab3530adf2ed6082622dc"): "5ccc2df60e2e5e011fbd5aa099e2cf1ece1803a96706acce85599e596c935609",
    }

    @staticmethod
    def uses_digest(step):
        fields = {k: step.get(k) for k in ("uses", "with", "env", "if", "id", "continue-on-error", "timeout-minutes")}
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    def test_uses_steps_reachable_in_dry_run_mode_are_pinned(self):
        reachable = {
            (job_name, index, step["uses"]): self.uses_digest(step)
            for job_name, job in self.workflow["jobs"].items()
            if not self.excludes_dry_run(job.get("if"))
            for index, step in enumerate(job.get("steps", []))
            if "uses" in step and not self.excludes_dry_run(step.get("if"))
        }
        self.assertEqual(reachable, self.DRY_RUN_REACHABLE_USES_STEPS)

    def test_dry_run_execution_context_is_reviewed(self):
        self.assertEqual(self.context_digest(), self.DRY_RUN_CONTEXT_DIGEST)
        # A job-level concurrency block would replace the workflow-level prod-train group for that job.
        for name, job in self.workflow["jobs"].items():
            self.assertNotIn("concurrency", job, name)

    def test_run_steps_reachable_in_dry_run_mode_are_reviewed(self):
        reachable = {
            (job_name, index, step.get("name")): step
            for job_name, job in self.workflow["jobs"].items()
            if not self.excludes_dry_run(job.get("if"))
            for index, step in enumerate(job.get("steps", []))
            if "run" in step and not self.excludes_dry_run(step.get("if"))
        }
        digests = {key: self.step_digest(step) for key, step in reachable.items()}
        self.assertEqual(digests, self.DRY_RUN_REACHABLE_RUN_STEPS)
        self.assertEqual(reachable[("deploy", 11, None)]["run"].strip(), "gcloud auth configure-docker")
        for key, step in reachable.items():
            with self.subTest(step=key):
                self.assertFalse(self.writes(step["run"]))

    def test_gcloud_mutations_count_as_writes(self):
        for run in ("gcloud container clusters resize c --num-nodes 0", "gcloud run deploy x", "gcloud iam roles update r"):
            self.assertTrue(self.writes(run), run)

    def unreviewed_uses(self, workflow):
        """uses: entries, in any job, that can run in dry-run mode without being on the reviewed list."""
        found = []
        for job_name, job in workflow["jobs"].items():
            if self.excludes_dry_run(job.get("if")):
                continue
            if "uses" in job:  # a job-level reusable workflow is unreviewed code
                found.append((job_name, job["uses"]))
            for step in job.get("steps", []):
                if "uses" in step:
                    if step["uses"] not in self.READ_ONLY_ACTIONS and not self.excludes_dry_run(step.get("if")):
                        found.append((job_name, step["uses"]))
                elif "run" not in step:
                    found.append((job_name, step))
        return found

    def test_every_uses_step_is_reviewed_or_excluded_from_dry_run_mode(self):
        self.assertEqual(self.unreviewed_uses(self.workflow), [])

    def test_uses_check_covers_every_job(self):
        for extra in ({"steps": [{"uses": "example/mutating-action@v1"}]}, {"uses": "example/.github/workflows/w.yml@v1"}):
            workflow = copy.deepcopy(self.workflow)
            workflow["jobs"]["extra"] = extra
            self.assertTrue(self.unreviewed_uses(workflow), extra)

    def test_every_write_step_is_excluded_from_dry_run_mode(self):
        writers = [s for s in self.steps if self.writes(s.get("run", ""))]
        self.assertTrue(writers)
        for step in writers:
            with self.subTest(step=step.get("name")):
                self.assertTrue(self.excludes_dry_run(step.get("if")), step.get("if"))
        for name in ("Verify rollout", "Verify preserved worker runtime and sibling bindings"):
            self.assertTrue(self.excludes_dry_run(self.step(name).get("if")))

    def test_exclusion_must_be_a_top_level_conjunct(self):
        for condition in ("inputs.worker_dry_run != true", "a == 1 && inputs.worker_dry_run != true",
                          "(a || b) && inputs.worker_dry_run != true"):
            self.assertTrue(self.excludes_dry_run(condition), condition)
        for condition in (None, "", "always() || inputs.worker_dry_run != true",
                          "a || b && inputs.worker_dry_run != true", "inputs.worker_dry_run != true || always()",
                          "(a && inputs.worker_dry_run != true) || always()", "${{ inputs.worker_dry_run != true }}",
                          "a) || (b && inputs.worker_dry_run != true"):
            self.assertFalse(self.excludes_dry_run(condition), condition)

    def test_dry_run_step_sets_mode_env_and_calls_only_the_dry_run_command(self):
        step = self.step("Dry-run worker image preserving live runtime")
        self.assertEqual(step["if"], "inputs.preserve_live_worker == true && inputs.worker_dry_run == true")
        self.assertEqual(step["env"], {
            "LIVE_BASELINE": "${{ inputs.worker_live_baseline }}",
            "ROLLBACK_RECEIPT": "${{ inputs.worker_rollback_receipt }}",
            "IMAGE_REPOSITORY": "${{ steps.target.outputs.image_repository }}",
            "IMAGE_DIGEST": "${{ steps.promote.outputs.image_digest }}",
            worker_env_name(): "1",
        })
        self.assertIn("worker_image_only.py dry-run", step["run"])
        self.assertFalse(self.writes(step["run"]))
        names = [s.get("name") for s in self.steps]
        for gate in ("Select merged production source and image tag", "Verify serving Firestore indexes", "Verify promoted worker digest"):
            self.assertLess(names.index(gate), names.index(step["name"]))
        self.assertNotIn("continue-on-error", step)

    INPUTS_DIGEST = "dadaf25a68f829315917b6df7ce00546bbd752e7900df5aced1ea20c5b99e701"

    def test_registry_read_reachable_in_dry_run_is_time_bounded(self):
        # The mode holds prod-train; a hung registry read must not hold it for the whole job cap.
        step = self.step("Verify promoted worker digest")
        self.assertLessEqual(step.get("timeout-minutes", 999), 5)

    def test_dry_run_input_is_declared_and_validated(self):
        inputs = self.workflow[True]["workflow_dispatch"]["inputs"] if True in self.workflow else self.workflow["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["worker_dry_run"]["type"], "boolean")
        self.assertFalse(inputs["worker_dry_run"]["default"])
        self.assertLessEqual(len(inputs), 10)  # GitHub's workflow_dispatch input limit
        # Every input's declaration (type, default, required, options) is reviewed with this mode.
        self.assertEqual(hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(), self.INPUTS_DIGEST)
        step = self.step("Validate Environment Input")
        script = step["run"].replace("${{ github.event.inputs.environment }}", "prod").replace("${{ inputs.environment }}", "prod")
        digest = "sha256:" + "1" * 64
        for preserve, image, break_glass, receipt, service, expected in (
            ("true", digest, "false", "", "batch-pipeline-worker", 0),
            ("false", digest, "false", "", "batch-pipeline-worker", 1),
            ("true", "", "false", "", "batch-pipeline-worker", 1),       # dry-run never builds or pushes
            ("true", digest, "true", "", "batch-pipeline-worker", 1),    # dry-run must hold the shared lock
            ("true", digest, "false", "{}", "batch-pipeline-worker", 0),  # receipt-bound inverse rehearsal
        ):
            with self.subTest(preserve=preserve, image=image, break_glass=break_glass, receipt=receipt):
                result = subprocess.run(["bash", "-e", "-c", script], capture_output=True,
                    env={"SERVICE": service, "PRESERVE_LIVE": preserve, "LIVE_BASELINE": "{}", "ROLLBACK_RECEIPT": receipt,
                         "SOURCE_REF": "a" * 40, "CANDIDATE_DIGEST": image, "BREAK_GLASS_LOCK": break_glass, "DRY_RUN": "true"})
                self.assertEqual(result.returncode, expected)
        dev = step["run"].replace("${{ github.event.inputs.environment }}", "development").replace("${{ inputs.environment }}", "development")
        result = subprocess.run(["bash", "-e", "-c", dev], capture_output=True, text=True,
            env={"SERVICE": "batch-pipeline-worker", "PRESERVE_LIVE": "false", "LIVE_BASELINE": "", "ROLLBACK_RECEIPT": "",
                 "SOURCE_REF": "a" * 40, "CANDIDATE_DIGEST": digest, "BREAK_GLASS_LOCK": "false", "DRY_RUN": "true"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worker_dry_run requires prod", result.stderr)

    def test_dry_run_notifications_are_marked(self):
        for name in ("Generate deployment summary", "Notify deployment status on Telegram"):
            self.assertIn("DRY-RUN (no write)", self.step(name)["with"]["release_version"])

    def test_dry_run_keeps_the_shared_prod_train_lock(self):
        group = self.workflow["concurrency"]["group"]
        self.assertIn("'prod-train'", group)
        self.assertNotIn("worker_dry_run", group)  # the dry-run never escapes the shared lock


if __name__ == "__main__":
    unittest.main()
