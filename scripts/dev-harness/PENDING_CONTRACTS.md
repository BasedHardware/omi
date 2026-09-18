# Executable spine contracts

`python3 scripts/check_spine_contracts.py` checks protection and prints every
pending marker with its builder package. Python contracts live in
`scripts/dev-harness/tests/spine/`; Dart contracts in `app/test/spine/`.
Both existing owner suites discover these directories. This command is also
in the local/CI checks manifest. No separate test runner or ceremony.

Python: put `@pending("V1")` on each test, imported from `.pending`.
Either quote style is recognized; builder markers must be standalone literals.
Active MECHANISM-owned tests may exercise dynamic calls to the marker API.
It is pytest `xfail(strict=True)`: the body executes, expected assertion or
skeleton failure is visible, unexpected success fails. Fixture/runtime errors
are not expected failures. Parametrized cases are individually strict.
Dart: use `contractTest(name, body)` from `test/support/spine/contract.dart`;
put `pendingContract('C1');` on its own line first inside the body. This survives
Dart formatting (a named argument gets folded onto another line). The async body
executes in its own zone; assertions/UnimplementedError print PENDING;
success throws XPASS outside the catch. Ordinary errors still fail. Use
awaited assertions. Compare collection-bearing Dart records field by field:
record equality compares Map identity; pass the Map itself to `expect`. Compile/load errors happen before the wrapper and fail the
owner suite; overriding `noSuchMethod` in a fake is valid Dart, not a compile bypass.

Widget contracts use `contractWidgets` from `app/test/support/spine/widgets.dart`.
Plain skip is forbidden; unexpected runtime/framework/teardown errors stay red.

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

The smallest immutable boundary is the **whole oracle**: registered spine tests,
fixtures and support code, including setup and assertions, with only whole pending
marker lines removable. Assertions alone are insufficient: changing a fixture or
not executing a test also weakens it. Registry owners and reviewed revision
records remain immutable; the exact before/after SHA256 pins are unchanged.
Protect authorized **content and obligations**, not incidental history: runner
edits, parent order, formatter-equivalent introductions and rejected proposals
must not invent new obligations. Formatting still needs an exact pinned revision.

Register every oracle in `contracts/spine/files.json`. Resolve introductions and
revision payloads from **all reachable history**, never a single simplified
history path or a selected parent. Match revision payloads by their pinned digest;
conflicting introductions/owners/records fail closed. A prefix whose records are
already accepted by the target may start from an exact pinned target-tree version,
even when an older branch introduction survives and squash erased intermediate
payloads. New revision tails still require exact payloads and preserved markers.
Retired markers cannot return on either parent order. Missing/shallow history
requires fetching it, never rebaselining.

A builder removes markers and makes those same tests pass. Corrections append
`contracts/spine/revisions/NNN-description.json` with path, owner, before/after
SHA256 and reason, preserving pending markers. An exceptional already-introduced
marker-free rendering may additionally be pinned as `retired_sha256` (for example,
formatter output with its unused marker import removed). This admits only those
exact bytes, never general formatting/import edits, and cannot restore markers. A revision PR may change only
oracle paths, design/check machinery and already accepted skeleton bytes;
splitting revision and implementation into two commits still fails. Restore a
changed oracle on a builder PR and send its reproduction to the spine.
Append-only means records accepted by the target or introduced in a scope-eligible
whole proposal, not every historical addition. Reverting a rejected mixed proposal
removes no authorized record. Eligibility is not proof of human review; coordinator
review remains authoritative. Deleting an authorized record still fails.

Shared shell runners are declared separately in `contracts/spine/runners.json`.
Their invocation contract, not their file hash, is protected: fail-fast, direct
unconditional suite commands with the required defines and discovery scope.
The constrained shell check rejects commented/conditional/filtered invocations,
early successful exits and command shadowing; it is not a general shell proof or
sandbox. Keep dispatch direct; new indirection needs a reviewed invocation rule.
Main may add guards/logging around those calls. A runner cannot also be an oracle.
The runner declarations are immutable, like the legacy revision-scope snapshot;
no builder can add its implementation to either allowlist. Spine-owned skeletons
retain exact-byte pins. `shared-prefixes.json` separately freezes an existing
scaffold prefix on a shared implementation file: its remaining bytes must equal
the accepted target exactly. Main’s body edits therefore survive; proposed body
edits cannot accompany an oracle revision. Declarations are immutable and cannot
classify an oracle as shared. The runner/checker and pure-oracle PRs
still require coordinator review: Git cannot authenticate reviewer roles or stop
a malicious replacement of the checker itself.

All spine ratchets constrain only files already migrated to that pattern (no
regression after adoption), plus at most brand-new files. Legacy debt growth in
unmigrated files never blocks ordinary work. Record adoption explicitly with the
behavioral acceptance tests; inventory counts alone do not imply adoption.
