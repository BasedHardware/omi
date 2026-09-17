# Executable spine contracts

`python3 scripts/check_spine_contracts.py` lists every pending marker with its
builder package and checks protection, locally and in the checks manifest.
Owner suites discover `scripts/dev-harness/tests/spine/` and `app/test/spine/`.
Register tests, fixtures and support in `contracts/spine/files.json`.

Python: `@pending("V1")` from `.pending` uses pytest strict xfail, including each
parametrized case. Dart: `contractTest(name, body)` from
`test/support/spine/contract.dart`, with standalone `pendingContract('C1');`
first inside the body. Await assertions. Python accepts AssertionError,
pytest.fail and NotImplementedError; Dart accepts TestFailure and UnimplementedError.
Success is XPASS and fails until the marker is removed. Compile/load and other
runtime errors stay red; `implements` with overridden noSuchMethod is valid Dart.

**Pending green means an executed, unmet contract, not a verified feature or a
correct oracle.** Missing behavior in existing code fails assertions without
throwing a stub error (B0 registration and C1 preference forwarding). An exception
class cannot distinguish a wrong implementation from a wrong expected value;
accepting only stub errors would ban those regression contracts, not detect rot.
A body may stop at its first failure; later assertions have not necessarily run.
Review failures against the specification, and exercise new oracles against a
satisfying implementation and a violating mutation where available. Report
oracle defects with reproductions before retirement; XFAIL counts prove neither
implementation nor oracle correctness. Diagnose with pytest --runxfail or local
marker removal, without editing assertions. Both languages have the same meaning.

The immutable boundary is the **whole oracle**, including setup and fixtures:
changing inputs or suppressing execution also weakens assertions. Only whole
pending-marker lines may be removed. Registry owners, revision records and exact
before/after SHA256 pins remain immutable. Runner bytes and parent order are not
an oracle. Resolve introductions and pinned revision payloads from all reachable
history; reject conflicting introductions/owners/records. Squashes absorb only a
revision prefix ending at its exact accepted digest. Retired markers cannot return
on branch heads or base-first merges. Missing history requires fetching, not rebaselining.

Builders remove markers and pass otherwise unchanged tests. Spine corrections
append `contracts/spine/revisions/NNN-description.json` with path, owner,
before/after hashes and reason, preserving markers. Revision PRs contain only
oracle paths, design/check machinery and accepted skeleton bytes; separating
revision and implementation commits within one PR still fails. Builders restore
the oracle and send the reproduction to the spine.

Shared shell runners declare immutable obligations in `contracts/spine/runners.json`:
fail-fast, direct unconditional suite commands, required defines and discovery
scope. Main may add guards/logging without preserving file hashes. A runner cannot
also be an oracle. The constrained shell check rejects commented/conditional/filtered
calls, early success and command shadowing; it is not a shell proof or sandbox.
Indirection needs a reviewed invocation rule. Neither runner declarations nor the
legacy revision-scope snapshot can be expanded by a builder. Spine-owned skeletons
retain exact-byte scope pins. Checker changes and pure-oracle PRs still need
coordinator review: Git cannot authenticate reviewers or prevent replacing the checker.

All spine ratchets constrain only explicitly adopted files (no regression after
migration), plus at most brand-new files. Legacy debt growth in unmigrated files
never blocks ordinary work. Record adoption with behavioral acceptance; inventory
counts alone do not imply it.
