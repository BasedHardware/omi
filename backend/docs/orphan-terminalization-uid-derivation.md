# Orphan terminalization uid derivation

Finalization's orphan sweep terminalizes crash orphans through a
generation-fenced transaction
(``database.conversation_finalization_jobs._complete_orphan_conversation_txn``).
The transaction's signature admits a caller that does not know the uid up
front (``uid: str | None = None``): when the uid argument is missing, the
terminal derives it from the document reference path
(``users/{uid}/conversations/{conversation_id}``) so the kept row still
receives its deterministic title via ``kept_row_terminal_update``.

## The defect

The uid-derivation call referenced ``_uid_from_conversation_path`` — an
underscore-prefixed name that exists nowhere in the tree. The shared parser is
``database.conversation_finalization_values.uid_from_conversation_path``, and
the recovery copy of the same transaction
(``database/conversation_processing_recovery.py``) imports and calls it
correctly. Any uid-less entry into the jobs copy therefore died with
``NameError`` inside the transaction: no terminal write, no title, the crash
orphan still ``processing``, and the sweep family retrying the same row every
window. Because the broken branch sat behind the ``uid or ...`` short-circuit,
every caller that passes an explicit uid (all current call sites) masked it —
the mock-at-the-call-site trap: the only tests drove the txn with the uid
filled in, so the NameError never surfaced in the suite.

## The fix

Call the shared parser. Pinned by
``backend/tests/unit/test_orphan_terminalization_uid_derivation.py``: the
uid-less derivation (including garbage, project-prefixed, and missing path
shapes that must still terminalize status-only), the generation/ownership
fence, jobs-vs-recovery parity, and the deterministic-title terminal the
derived uid feeds.

## Same review batch (merge-readiness remediation)

- ``routers/listen/transcripts.py``: the oversized-rollover probe now binds its
  escape through a typed resolver (``_resolve_rollover_escape``, coroutine
  functions only). The old ``callable()`` guard awaited any callable and a
  mistyped attribute burned the probe on a swallowed ``TypeError`` instead of
  taking the plain-rollover fallback.
- ``database/_client.py``: the duplicated ``google.api_core.exceptions`` import
  block is consolidated and the availability-classifier re-export is explicit
  (``as``-form) so the static gate reads it as intentional; the five test
  modules that import it from ``database._client`` keep working.
- ``routers/pusher.py``: three unused imports removed (static-gate failures on
  the open PR).
- ``tests/fast_unit_duration_allowlist.txt``: the real-gateway-client
  construction proof in ``test_chat_metadata_foreground_deadline.py`` measures
  at the 1.0s CPU threshold under file isolation and is grandfathered.

Failure-Class: FC-terminal-leaves-kept-row-untitled — a server terminal that
moves a conversation into the default list must leave it carrying something
useful (a title); the undefined-name crash aborted the terminal write instead
of stamping the kept row.
