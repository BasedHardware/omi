# STM-note integrator ingestion contract

Status: production-neutral mapping and acceptance adapter; no HTTP/MCP route,
worker, or activation (2026-08-13).

`apps/service/stm/stm-note-ingestion.ts` maps every authenticated MCP/HTTP
memory write to a **user-asserted STM note** and the existing durable
formation-work acceptance port.

## Exact seal

One write binds the account, integrator `write_id`, exact content bytes,
`write_door` (`http` | `mcp` | `mcp_legacy`), optional `client_write_ref`,
and `submitted_at`. The account/write-derived formation work id is stable on
replay; note and content digests change when bound bytes change.

## Authority

- `source_trust` is `user_asserted`; capture kind is `user_asserted_stm_note`.
- Producer-null `integrator-channel:submitter` source identity only.
- No owner identity, entity binding, `subject:*` label, or identity authority.
- `identity_authority_context` remains null in the formation snapshot.
- Formation is still required before any grouped/query product state exists.

## Deliberate production gap

No HTTP/MCP route, credential verification, legacy card compatibility shim,
worker, or scheduler calls this adapter. Live create/edit/delete card semantics
remain unmapped until a separately authorized compatibility layer lands.
