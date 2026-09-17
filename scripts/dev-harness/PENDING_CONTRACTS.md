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
awaited assertions. Compile/load errors happen before the wrapper and fail the
owner suite; overriding `noSuchMethod` in a fake is valid Dart, not a compile bypass.

The smallest immutable boundary is the **whole oracle**: registered spine tests,
fixtures and support code, including setup and assertions, with only whole pending
marker lines removable. Assertions alone are insufficient: changing a fixture or
not executing a test also weakens it. Registry owners and reviewed revision
records remain immutable; the exact before/after SHA256 pins are unchanged.
Neither shared runner bytes nor parent ordering is an oracle.

Register every oracle in `contracts/spine/files.json`. Resolve introductions and
revision payloads from **all reachable history**, never a single simplified
history path or a selected parent. Match revision payloads by their pinned digest;
conflicting introductions/owners/records fail closed. A squash may absorb only a
revision prefix ending at an exact accepted digest. Retired marker occurrences
cannot return on either a branch head or a base-first PR merge. Missing/shallow
history requires fetching it, never rebaselining.

A builder removes markers and makes those same tests pass. Corrections append
`contracts/spine/revisions/NNN-description.json` with path, owner, before/after
SHA256 and reason, preserving pending markers. A revision PR may change only
oracle paths, design/check machinery and already accepted skeleton bytes;
splitting revision and implementation into two commits still fails. Restore a
changed oracle on a builder PR and send its reproduction to the spine.

Shared shell runners are declared separately in `contracts/spine/runners.json`.
Their invocation contract, not their file hash, is protected: fail-fast, direct
unconditional suite commands with the required defines and discovery scope.
The constrained shell check rejects commented/conditional/filtered invocations,
early successful exits and command shadowing; it is not a general shell proof or
sandbox. Keep dispatch direct; new indirection needs a reviewed invocation rule.
Main may add guards/logging around those calls. A runner cannot also be an oracle.
The runner declarations are immutable, like the legacy revision-scope snapshot;
no builder can add its implementation to either allowlist. Spine-owned skeletons
retain the existing exact-byte scope pins. The runner/checker and pure-oracle PRs
still require coordinator review: Git cannot authenticate reviewer roles or stop
a malicious replacement of the checker itself.

All spine ratchets constrain only files already migrated to that pattern (no
regression after adoption), plus at most brand-new files. Legacy debt growth in
unmigrated files never blocks ordinary work. Record adoption explicitly with the
behavioral acceptance tests; inventory counts alone do not imply adoption.
