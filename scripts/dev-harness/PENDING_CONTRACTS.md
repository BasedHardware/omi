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
awaited assertions; `testWidgets`/skip are not supported pending markers.

Register each file (including helper/fixture files) in `contracts/spine/files.json`.
The check resolves the file's **introducing Git commit**, reads its bytes with
`git show`, and permits only deletion of whole pending-marker lines. Removing,
renaming, editing assertions, re-adding a removed marker, or changing an existing
registry owner fails. New contracts can be added; no baseline update flag exists.
The introducing commit is the spine commit (regular merges retain it).
A shallow checkout missing that commit must fetch history, never rebaseline.
New files not yet in HEAD can be checked before their first local commit.

A builder removes markers and makes these same tests pass. A mistaken contract
comes back to the owning spine for a reviewed contract revision/version, not a
builder rewrite. This mechanism is for the explicitly requested mobile program;
it is not a general exemption from the repository's regression-test rules.
