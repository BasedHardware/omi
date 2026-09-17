# Executable spine contracts

`python3 scripts/check_spine_contracts.py` checks protection and prints every
pending marker with its builder package. Python contracts live in
`scripts/dev-harness/tests/spine/`; Dart contracts in `app/test/spine/`.
Both existing owner suites discover these directories. This command is also
in the local/CI checks manifest. No separate test runner or ceremony.

Python: put `@pending("V1")` on each test, imported from `.pending`.
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

Register each file (including helper/fixture files) in `contracts/spine/files.json`.
The check resolves the file's **introducing Git commit**, reads its bytes with
`git show`, and permits only deletion of whole pending-marker lines. Removing,
renaming, editing assertions, re-adding a removed marker, or changing an existing
registry owner fails. New contracts can be added; no baseline update flag exists.
The introducing commit is the spine commit; squash merges pin its final bytes.
A shallow checkout missing that commit must fetch history, never rebaseline.
New files not yet in HEAD can be checked before their first local commit.

A builder removes markers and makes these same tests pass. A mistaken contract
comes back to the owning spine for a reviewed contract revision/version, not a
builder rewrite. This mechanism is for the explicitly requested mobile program;
it is not a general exemption from the repository's regression-test rules.

Spine-only corrections append `contracts/spine/revisions/NNN-description.json`
with path, owner, before/after SHA256 and review reason, in the same commit as
exact corrected bytes. The check pins that commit automatically, validates the
hash chain and forbids editing/deleting committed records. A squash absorbs only
a revision prefix ending at the introducing file's exact digest. Pending markers must
stay unchanged in that revision; retire them separately. Builders cannot use
revision records to accept their implementation: the owning spine and coordinator
review the changed oracle, just as changes to this checker require review. Git
cannot authenticate reviewer roles; this explicit review boundary is not a bypass
flag. Subsequent edits still permit only marker removal against the revised oracle.

All spine ratchets constrain only files already migrated to that pattern (no
regression after adoption), plus at most brand-new files. Legacy debt growth in
unmigrated files never blocks ordinary work. Record adoption explicitly with the
behavioral acceptance tests; inventory counts alone do not imply adoption.
