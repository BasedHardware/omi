"""Offline behavioral fixtures for the SCA-2149 preservation primitive."""

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess

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
            lambda o: o["spec"]["strategy"].update(type="RollingUpdate"),
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
        self.assertEqual(helm["if"], "inputs.preserve_live_worker != true")
        self.assertEqual(writer["if"], "inputs.preserve_live_worker == true")
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


if __name__ == "__main__":
    unittest.main()
