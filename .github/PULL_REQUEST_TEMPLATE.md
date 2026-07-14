<!-- Keep this short and honest. Reviewers read the Verification section first. -->

## What changed and why

<!-- One or two sentences. Link the issue if there is one. -->

## Product invariants affected

<!-- Name locked invariant IDs this PR touches (e.g. INV-CHAT-1), or "none".
     Registry: docs/product/invariants/ — required when changing paths listed
     on a locked invariant. -->

## How it was verified

<!-- The commands you ran and what they showed. Exercising the real user-facing
     path counts as verification; compiling or lint passing does not.
     If something could not be verified, say so explicitly. -->

## Tests

<!-- Bug fix: point to the regression test that would have caught the bug.
     Feature: point to the tests for the core path and main error path.
     No test change: explain why none was needed. -->

## Root cause and durable guard (bug fixes)

<!-- Name the violated contract, similar recent failures you checked, and the
     shared state model / harness / compatibility check / static guard that
     prevents this failure class. If a risky migration is deliberately separate,
     link its tracking issue and explain the rollback boundary. -->

## Scoped cleanups (optional)

<!-- Related fixes you made along the way (see AGENTS.md → "Leave It Better
     Than You Found It"). Each should be its own commit and verifiable. -->
