# TRADEOFF MEMO: MCP final reauthorization receipt

Status: incomplete disposable draft; not applied to runtime.

## Purpose

The current MCP handler reauthorizes immediately before positive bytes, but it
does not receive the authorization generation used to build the page. A grant
can remain generally allowed while changing generation between the application
read fence and wire emission.

The patch sketches an internal, content-free receipt carried from `readPage`
to `reauthorizeBeforeEmission`. The receipt is never serialized in the page.

## Why it is not integrated

The patch changes the protocol port but does not update its consumers or tests.
Its six-field receipt mirrors the unresolved AuthorizedContext draft. It must
not become runtime authority until the published authorization model defines
which coordinates the final fence must compare.

## Decision needed

Decide whether the final fence uses the existing opaque authorization/grant/
account coordinates or a newly ratified ADR-010 context. Then update protocol,
application composition, and adversarial tests together. Required tests include
coordinate change denial, hostile receipt rejection without accessor execution,
receipt non-serialization, and successful emission for an exact unchanged
receipt.

