# Synthetic API-shaped Pod fixture

`pod-api-response.json` is authored independently of `render()` and contains no
production capture, credentials or account data. Its node, UID, version and time
are synthetic. It models core/v1 JSON serialization and standard service-account
and scheduling defaults; it is not evidence of live admission or execution.

In particular, the non-pointer `hostNetwork`, `hostPID` and `hostIPC` booleans
have `omitempty` JSON tags and default false in the
[Kubernetes PodSpec type](https://github.com/kubernetes/api/blob/master/core/v1/types.go).
Their absence differs from the explicit false fields in the create manifest.
The fixture includes the standard KSA projected volume and API defaults. Tests
must load this file directly, never regenerate it from the renderer under test.

Its explicit `us-central1` region and `us-central1-a` zone labels model the
two topology labels observed in the 2026-11-16 admission dry-run. Only those
reviewed string values are accepted; this synthetic fixture proves no current
node placement. Release must independently refresh node UID and topology.

The image fields pin the current candidate from `readiness_contract.py`. Updating
that identity does not turn this synthetic serialization fixture into evidence
of native qualification, live admission or execution.
