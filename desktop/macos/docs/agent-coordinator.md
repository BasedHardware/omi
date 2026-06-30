# Desktop Agent Coordinator

This document locks the Phase 0 boundary for the macOS Desktop Agent Coordinator. It extends the local agent control-plane model described in [Agent Control Plane](../../../docs/doc/developer/agent-control-plane.mdx) and follows the desktop development constraints in [desktop/macos/AGENTS.md](../AGENTS.md).

## Scope

The first coordinator wave is macOS Desktop only. Backend canonical AgentRun APIs, mobile unification, AgentVM runtime-node work, cloud relay/directory work, public MCP coordinator controls, cross-device artifact sync, full artifact browsing, model-assisted routing, and full floating-pill replacement are deferred. Track follow-up work in repo issues or checked-in planning docs before implementation.

The coordinator uses the existing TypeScript desktop runtime kernel as the execution substrate and `omi-agentd.sqlite3` as the only durable local agent/coordinator authority. Swift is a projection and control-client layer through `AgentRuntimeProcess` / `AgentBridge`; it may cache UI projections, but it must not own run success, failure, approval, grant, or artifact-delivery truth.

## Roles

- **TypeScript runtime kernel:** owns `AgentSession`, `AgentRun`, `RunAttempt`, `AdapterBinding`, events, artifacts, delegations, grants, terminal state, and future coordinator tables in `omi-agentd.sqlite3`.
- **Desktop Coordinator:** owns deterministic routing, scoped context packets, dispatch decisions, lifecycle monitoring, approval/artifact/memory/task candidate projection, and the derived action queue.
- **Swift app:** renders Ask Omi, task chat, voice, floating-pill, and future Agents & Attention surfaces; sends control/query requests; displays projections from kernel/coordinator state.
- **Adapters:** execute attempts and request capabilities. They never approve grants or establish product lifecycle truth.

## Core Invariants

1. No second lifecycle authority: the TypeScript runtime kernel and `omi-agentd.sqlite3` remain authoritative for local execution state.
2. Coordinator durable state extends `omi-agentd.sqlite3` through migrations; do not create a separate coordinator database.
3. Swift/UI state is a projection. UI dismissal, local success helpers, voice refs, pill state, or adapter-native IDs never imply kernel success or failure.
4. `DesktopActionQueueItem` is derived, not persisted authority. It is computed from runs, dispatches, artifact deliveries, memory/task candidates, task-chat waiting states, legacy pill projections, and attention overrides.
5. Worker prompts must come from explicit `DesktopContextPacket` records with provenance, redacted preview, hash, TTL, retention class, and audit rows.
6. Policy owns grants and approvals. Adapters describe capability requests; only local policy may approve, deny, create grants, consume grants, or write approval events.
7. Screenshots, screen history, and broad local context are sensitive. Screenshot image bytes or broad screen access require explicit policy allow or dispatch.
8. Agents create memory/task candidates unless the user made an explicit unambiguous command and policy allows direct mutation.
9. Surface state is not execution state: Ask Omi, task chat, floating pills, voice refs, and adapter-native session IDs are views or transport details.
10. Desktop first: backend/mobile/cloud/AgentVM/public MCP coordinator work stays out of this wave.

## Phase 0 Decisions

- Task chat should become a canonical task-chat session bound to `surfaceKind=task_chat`, `externalRefKind=task`, and the task id; legacy ACP resume IDs stay separate from Omi session IDs.
- Main chat is the canonical user-facing conversation envelope for new typed routing. Typed main-chat turns may ask the coordinator for route context before the normal bridge call, but the bridge still produces the assistant response and child task/subagent runtime sessions remain isolated and auditable.
- PTT/realtime turns are mirrored into main chat history after completion, but realtime reasoning still uses its warm voice path. True single-chat parity requires routing final PTT transcripts through the same parent-turn coordinator contract before removing separate voice/subagent affordances.
- Floating pill replacement is deferred. Wave one may project legacy pill state into awareness/action-queue views and expose safe inspect/cancel/open actions, but `spawn_agent` / `manage_agent_pills` remain legacy workflows until a later replacement phase.
- `DesktopAutomationBridge` and `scripts/omi-ctl` are verification and development substrates, documented in [desktop e2e](../e2e/SKILL.md) and [harness](../e2e/harness.md). They are not production coordinator actuators unless a separate approval path is added.
- Local Agent API expansion is deferred until scoped local credentials, Host/Origin checks, token rotation, and context-access logging are in place.
- Tool-manifest risk/privacy/bundle metadata is a classification contract for the coordinator. Grant enforcement lands with the local policy module; until then, do not treat metadata alone as an approval membrane.
