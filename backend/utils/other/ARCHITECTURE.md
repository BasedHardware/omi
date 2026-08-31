# `utils/other` — what actually lives here

A package named "other" collects whatever had no better home, so the useful thing a map can give is
not a file list — that goes stale the week it is written — but the **axis** the modules sit on and
where the boundaries are.

## The axis: leaves that talk to something outside the process

Almost everything here is a **leaf**: the last piece of our code before a request leaves for a cloud
service, a queue, or the caller's browser. Domain logic does not belong here; a module that starts
making product decisions has outgrown the package.

| what it faces | modules |
|---|---|
| object storage | `storage.py`, `local_storage.py`, `chat_file.py` |
| a vendor API | `hume.py`, `hume_callback_token.py` |
| the user's device | `notifications.py`, `endpoints.py` |
| our own deferred work | `task.py`, `jobs.py`, `deferred_delete.py` |
| calling-convention helpers | `backoff.py`, `timeout.py`, `list_budget.py` |

## Two boundaries worth knowing before you edit

**`storage.py` goes through a port, not a client.** Every object read and write resolves through
`_object_store()` and `_signed_url()`, so the bucket backend is configuration rather than an import
(ADR-0032). A new call that reaches for a vendor storage client directly is rejected by
`.github/scripts/check_oss_object_store_boundary.py`, not by review.

**`hume_callback_token.py` is a security primitive, not a Hume helper.** `POST /v1/agents/hume/callback`
cannot be authenticated the usual way — Hume calls it, and Hume holds no user token — so the token
minted here is the only thing binding a callback to a submission of ours. It is a separate module from
`hume.py` on purpose: it has its own test surface, and folding it into the vendor client would put a
signing key next to code whose job is to make outbound calls.

## Adding a module

Ask whether the thing you are adding faces outward. If it does, it belongs here and this table gains a
row. If it makes a decision about what the product should do, it belongs in the package that owns that
decision — `utils/conversations`, `utils/memory`, `utils/stt` — and putting it here only makes it
harder to find.
