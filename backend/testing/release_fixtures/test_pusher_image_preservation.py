"""Offline rehearsal of the image-only Pusher proposal. No Kubernetes or registry client."""

import copy
import json
import unittest
from dataclasses import dataclass, field

SHARED_MAP = "prod-omi-backend-config"
PUSHER = ("Deployment", "prod-omi-pusher")
OLD_IMAGE = "fixture.invalid/pusher@sha256:" + "a" * 64
NEW_IMAGE = "fixture.invalid/pusher@sha256:" + "b" * 64
SOURCE = "c" * 40
MEMO_FLAG = "FIXTURE_MEMO_ENABLED"
LEASE_KEY = "FIXTURE_LEASE_SECONDS"


class Refused(Exception):
    pass


@dataclass
class Snapshot:
    # The live adapter would have to prove coverage and writer exclusion.
    inventory_complete: bool = True
    writers_excluded: bool = True
    service_env_proven: bool = True
    revision: int = 1
    shared_map: dict = field(default_factory=lambda: {"EMPTY": "", "OVERRIDE": "fixture-from-map"})
    shared_map_revision: int = 1
    # The fixture models a secret dependency without using any real secret.
    secret: dict = field(default_factory=lambda: {"TOKEN": "fixture-private"})
    secret_revision: int = 1
    image_env: dict = field(
        default_factory=lambda: {OLD_IMAGE: {"APP_MODE": "fixture"}, NEW_IMAGE: {"APP_MODE": "fixture"}}
    )
    templates: dict = field(
        default_factory=lambda: {
            PUSHER: {
                "containers": [
                    {
                        "name": "pusher",
                        "image": OLD_IMAGE,
                        "envFrom": [{"configMapRef": {"name": SHARED_MAP}}],
                        "env": [
                            {"name": MEMO_FLAG, "value": "false"},
                            {"name": "OVERRIDE", "value": ""},
                            {
                                "name": "LEASE",
                                "valueFrom": {
                                    "configMapKeyRef": {
                                        "name": SHARED_MAP,
                                        "key": LEASE_KEY,
                                        "optional": True,
                                    }
                                },
                            },
                            {
                                "name": "TOKEN",
                                "valueFrom": {
                                    "secretKeyRef": {
                                        "name": "fixture-secret",
                                        "key": "TOKEN",
                                    }
                                },
                            },
                        ],
                    }
                ],
            },
            ("Deployment", "fixture-listen"): {
                "containers": [{"envFrom": [{"configMapRef": {"name": SHARED_MAP}}]}],
            },
            ("CronJob", "fixture-worker"): {
                "initContainers": [{"env": [{"valueFrom": {"configMapKeyRef": {"name": SHARED_MAP}}}]}],
            },
            ("DaemonSet", "fixture-observer"): {
                "volumes": [{"projected": {"sources": [{"configMap": {"name": SHARED_MAP}}]}}],
            },
            ("Pod", "fixture-direct"): {
                "volumes": [{"configMap": {"name": SHARED_MAP}}],
            },
            ("StatefulSet", "fixture-unrelated"): {"containers": [{}]},
        }
    )


def references_shared_map(value):
    if isinstance(value, dict):
        return any(
            (
                key in {"configMap", "configMapRef", "configMapKeyRef"}
                and isinstance(item, dict)
                and item.get("name") == SHARED_MAP
            )
            or references_shared_map(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(map(references_shared_map, value))
    return False


def consumers(snapshot):
    return sorted(kind + "/" + name for (kind, name), spec in snapshot.templates.items() if references_shared_map(spec))


def referenced_data(snapshot, kind, name):
    stores = {("configmap", SHARED_MAP): snapshot.shared_map, ("secret", "fixture-secret"): snapshot.secret}
    return stores.get((kind, name))


def container_env(snapshot, container):
    """Resolve only the Kubernetes env inputs exercised by this fixture."""
    if not snapshot.service_env_proven or container["image"] not in snapshot.image_env:
        raise Refused("effective inputs unavailable")
    image_env = snapshot.image_env[container["image"]]
    env = {}
    for source in container.get("envFrom", []):
        prefix = source.get("prefix", "")
        data = None
        for ref_type, kind in (("configMapRef", "configmap"), ("secretRef", "secret")):
            if ref_type in source:
                ref = source[ref_type]
                data = referenced_data(snapshot, kind, ref["name"])
                if data is None and ref.get("optional"):
                    data = {}
                break
        if data is None:
            raise Refused("effective inputs unavailable")
        env.update((prefix + key, value) for key, value in data.items())
    names = set()
    for entry in container.get("env", []):
        name = entry["name"]
        if name in names:
            raise Refused("duplicate environment entry")
        names.add(name)
        if "valueFrom" not in entry:
            literal = entry.get("value", "")
            if "$" in literal:
                raise Refused("unsupported fixture expansion")
            env[name] = literal
            continue
        source = entry["valueFrom"]
        for ref_type, kind in (("configMapKeyRef", "configmap"), ("secretKeyRef", "secret")):
            if ref_type in source:
                ref = source[ref_type]
                data = referenced_data(snapshot, kind, ref["name"])
                if data is not None and ref["key"] in data:
                    env[name] = data[ref["key"]]
                elif not ref.get("optional"):
                    raise Refused("effective inputs unavailable")
                break
        else:
            raise Refused("unsupported fixture reference")
    return image_env | env


def pusher(spec):
    matches = [container for container in spec["containers"] if container["name"] == "pusher"]
    if len(matches) != 1:
        raise Refused("pusher container identity ambiguous")
    return matches[0]


def with_image(spec, image):
    result = copy.deepcopy(spec)
    pusher(result)["image"] = image
    return result


def prove(snapshot, before, expected_image, admitted, startup_env):
    if admitted != with_image(before, expected_image):
        raise Refused("admission changed more than the pusher image")
    if container_env(snapshot, pusher(admitted)) != startup_env:
        raise Refused("effective environment changed")


def preflight(baseline, current):
    if not current.inventory_complete or not current.writers_excluded:
        raise Refused("consumer coverage or writer exclusion unproven")
    if baseline != current:
        raise Refused("inputs changed since preview")


def preview(snapshot, admitted_candidate, qualified_source_image, startup_env):
    preflight(snapshot, snapshot)
    if qualified_source_image != (SOURCE, NEW_IMAGE):
        raise Refused("source and digest qualification mismatch")
    before = snapshot.templates[PUSHER]
    if container_env(snapshot, pusher(before)) != startup_env:
        raise Refused("running environment differs from replacement inputs")
    prove(snapshot, before, NEW_IMAGE, admitted_candidate, startup_env)
    if "Deployment/prod-omi-pusher" not in consumers(snapshot):
        raise Refused("shared reference missing")
    return {
        "fixture": True,
        "scope": "Deployment/prod-omi-pusher",
        "shared_configmap_consumers": consumers(snapshot),
        "effective_environment": "equal",
        "canary": "required",
        "rollback": "exact prior digest with the same config inputs",
    }


@dataclass(frozen=True)
class CanaryReceipt:
    snapshot: Snapshot = field(repr=False)
    qualified_source_image: tuple[str, str]


def rehearse_canary(snapshot, admitted_candidate, qualification, startup_env):
    preview(snapshot, admitted_candidate, qualification, startup_env)
    return CanaryReceipt(copy.deepcopy(snapshot), qualification)


def transition(current, expected, admitted, image, startup_env):
    """Fixture compare-and-swap. The production proposal requires server enforcement."""
    preflight(expected, current)
    prove(current, current.templates[PUSHER], image, admitted, startup_env)
    result = copy.deepcopy(current)
    result.revision += 1
    result.templates[PUSHER] = copy.deepcopy(admitted)
    return result


def promote(current, expected, admitted, startup_env, canary):
    if canary is None or canary.snapshot != expected or canary.qualified_source_image != (SOURCE, NEW_IMAGE):
        raise Refused("matching canary required")
    return transition(current, expected, admitted, NEW_IMAGE, startup_env)


def rollback(current, promoted, baseline, admitted, startup_env):
    old_template = baseline.templates[PUSHER]
    if promoted.templates[PUSHER] != with_image(old_template, NEW_IMAGE):
        raise Refused("rollback baseline mismatch")
    return transition(current, promoted, admitted, pusher(old_template)["image"], startup_env)


class PreservationTest(unittest.TestCase):
    def setUp(self):
        self.live = Snapshot()
        self.before = self.live.templates[PUSHER]
        self.candidate = with_image(self.before, NEW_IMAGE)
        self.startup_env = {
            "APP_MODE": "fixture",
            "EMPTY": "",
            "OVERRIDE": "",
            MEMO_FLAG: "false",
            "TOKEN": "fixture-private",
        }

    def preview(self, snapshot=None, admitted=None, qualification=(SOURCE, NEW_IMAGE)):
        return preview(snapshot or self.live, admitted or self.candidate, qualification, self.startup_env)

    def test_canary_replacement_and_exact_rollback(self):
        receipt = self.preview()
        self.assertEqual(
            receipt["shared_configmap_consumers"],
            [
                "CronJob/fixture-worker",
                "DaemonSet/fixture-observer",
                "Deployment/fixture-listen",
                "Deployment/prod-omi-pusher",
                "Pod/fixture-direct",
            ],
        )
        self.assertNotIn("fixture-private", json.dumps(receipt))
        self.assertNotIn(MEMO_FLAG, json.dumps(receipt))
        canary = rehearse_canary(self.live, self.candidate, (SOURCE, NEW_IMAGE), self.startup_env)
        canary_env = container_env(self.live, pusher(self.candidate))
        self.assertEqual(self.live.templates[PUSHER], self.before)
        promoted = promote(self.live, self.live, self.candidate, self.startup_env, canary)
        rolled_back = rollback(promoted, copy.deepcopy(promoted), self.live, self.before, self.startup_env)
        for env in (
            self.startup_env,
            canary_env,
            container_env(promoted, pusher(promoted.templates[PUSHER])),
            container_env(rolled_back, pusher(rolled_back.templates[PUSHER])),
        ):
            self.assertEqual(env, self.startup_env)
            self.assertEqual(env.get(MEMO_FLAG, "true"), "false")  # Missing flag defaults to on.
            self.assertNotIn("LEASE", env)
            self.assertNotIn(LEASE_KEY, env)
            self.assertEqual(env["EMPTY"], "")
        self.assertEqual(promoted.templates[PUSHER], self.candidate)
        self.assertEqual(rolled_back.templates, self.live.templates)
        self.assertEqual(rolled_back.revision, self.live.revision + 2)
        for state in (promoted, rolled_back):
            self.assertEqual(state.shared_map, self.live.shared_map)
            self.assertEqual(state.shared_map_revision, self.live.shared_map_revision)
            self.assertEqual(state.secret, self.live.secret)
            self.assertEqual(state.secret_revision, self.live.secret_revision)
            self.assertEqual(consumers(state), consumers(self.live))
            for identity in self.live.templates.keys() - {PUSHER}:
                self.assertEqual(state.templates[identity], self.live.templates[identity])
        print(json.dumps(receipt, sort_keys=True))

    def test_refuses_mutated_admission_or_unqualified_digest(self):
        for name in (MEMO_FLAG, "LEASE", "OVERRIDE"):
            with self.subTest(name=name):
                changed = copy.deepcopy(self.candidate)
                container = pusher(changed)
                container["env"] = [entry for entry in container["env"] if entry["name"] != name]
                with self.assertRaisesRegex(Refused, "admission changed"):
                    self.preview(admitted=changed)
        with self.assertRaisesRegex(Refused, "qualification mismatch"):
            self.preview(qualification=(SOURCE, OLD_IMAGE))

    def test_refuses_unknown_or_changed_effective_inputs(self):
        for field_name in ("inventory_complete", "writers_excluded", "service_env_proven"):
            with self.subTest(field=field_name):
                changed = copy.deepcopy(self.live)
                setattr(changed, field_name, False)
                with self.assertRaises(Refused):
                    self.preview(changed)
        changed = copy.deepcopy(self.live)
        changed.image_env[NEW_IMAGE]["LEASE"] = "fixture-default"
        with self.assertRaisesRegex(Refused, "effective environment changed"):
            self.preview(changed)
        del changed.image_env[NEW_IMAGE]
        with self.assertRaisesRegex(Refused, "effective inputs unavailable"):
            self.preview(changed)
        changed = copy.deepcopy(self.live)
        changed.shared_map["EMPTY"] = "changed-since-start"
        with self.assertRaisesRegex(Refused, "running environment differs"):
            self.preview(changed)

    def test_refuses_concurrent_change_or_failed_canary(self):
        expected = copy.deepcopy(self.live)
        canary = rehearse_canary(expected, self.candidate, (SOURCE, NEW_IMAGE), self.startup_env)
        with self.assertRaisesRegex(Refused, "matching canary required"):
            promote(self.live, expected, self.candidate, self.startup_env, None)
        for field_name in ("revision", "shared_map_revision", "secret_revision"):
            with self.subTest(field=field_name):
                changed = copy.deepcopy(self.live)
                setattr(changed, field_name, 2)
                with self.assertRaisesRegex(Refused, "inputs changed"):
                    promote(changed, expected, self.candidate, self.startup_env, canary)
        changed = copy.deepcopy(self.live)
        changed.templates[("Job", "new-consumer")] = changed.templates[("CronJob", "fixture-worker")]
        with self.assertRaisesRegex(Refused, "inputs changed"):
            promote(changed, expected, self.candidate, self.startup_env, canary)

        promoted = promote(self.live, expected, self.candidate, self.startup_env, canary)
        changed = copy.deepcopy(promoted)
        changed.revision += 1
        with self.assertRaisesRegex(Refused, "inputs changed"):
            rollback(changed, promoted, expected, self.before, self.startup_env)

        with self.assertRaisesRegex(Refused, "admission changed"):
            rollback(promoted, promoted, expected, self.candidate, self.startup_env)
        with self.assertRaisesRegex(Refused, "matching canary required"):
            promote(changed, changed, self.candidate, self.startup_env, canary)


if __name__ == "__main__":
    unittest.main()
