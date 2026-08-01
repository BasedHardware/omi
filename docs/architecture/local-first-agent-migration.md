# Migrating the agent to omi-v4's local-first architecture

Status: **plan, not yet implemented.** Branch `arch/local-first-agent`, based on `main`.

This is the migration design for retiring the per-user GCE "agent VM" and moving the
agent to the omi-v4 shape. Every claim about omi-v4 below was read out of
`~/projects/omi-v4` at commit `76040fdee4`; every claim about the current design was read
out of this repo. Facts are marked MEASURED; inferences are marked INFERRED.

---

## 1. The one question this turns on

**Is "ask about my screen history from a surface other than the Mac that recorded it" a
shipped promise?**

- **If no** → delete the VM. The user's data is already on the user's machine; shipping a
  copy to a rented machine so a rented agent can read it is a round trip with no
  destination. Everything below applies.
- **If yes** → the VM is doing real work, and this plan changes from "delete it" to
  "replace it with a shared server-side index." The migration steps are largely the same;
  only §6 differs.

Nothing else in this document is worth arguing about until that is answered.

---

## 2. What omi-v4 actually does

| | omi (today) | omi-v4 |
|---|---|---|
| Per-user compute | `e2-small` + 50 GB `pd-balanced` + public IP, one per user | **none** — one shared Cloudflare Worker |
| Agent location | FastAPI on the VM (`backend/agent_vm/main.py`) | in the client process (`app/native/hub/src/runtime.rs:2397`) |
| Agent data access | `execute_sql` over an uploaded copy of the whole DB | direct `MemoryDb` call, same address space (`runtime.rs:2196`) |
| Sync cadence | **every 3s**, 9 tables (`AgentSyncService.swift:123`) | 30s, and an idle tick costs **zero** network (`memory_sync.dart:185`) |
| Sync granularity | whole-DB gzip upload + row deltas, whole-DB re-upload on recovery | cursor-paged commit log, acked per commit |
| Screen frames | metadata + OCR + embeddings uploaded | **never leave the device** (`capture_upload.rs` ships audio only) |
| Semantic search | `SELECT … embedding FROM screenshots LIMIT 10000` + Python dot-product loop | Cloudflare Vectorize ANN, uid-filtered |
| Agent tool surface | arbitrary SQL, WebSearch, headless browser | 2 tools, both approval-gated |

MEASURED. A repo-wide grep of omi-v4 for every provisioning idiom — GCE,
`instances().insert`, machine types, Fly, Modal, Lambda, Cloud Run — returns nothing.

**The caveat that matters:** omi-v4 does **not implement the feature the VM exists to
serve.** Its Rewind timeline is local-only and the chat agent cannot query it —
`CaptureSource::Screen` is defined in the signal enum but no Dart code emits it. So v4
does not prove the VM is unnecessary; it proves v4 does not have that workload. We would
be building the missing half, not copying it.

---

## 3. Principles being adopted

1. **The device is the source of truth.** The server holds a rebuildable projection, never
   the only copy.
2. **Compute goes to the data, not the reverse.** The agent runs where the database
   already is.
3. **Sync is an event log, not a file copy.** Cursor-paged commits, acked individually,
   idempotent on replay. An idle client costs nothing.
4. **Screen frames never leave the device.** Only derived, consented artifacts sync.
5. **The agent's tool surface is small and approval-gated.** Arbitrary SQL against the
   user's whole history is not a tool, it is a liability.

---

## 4. Migration phases

Each phase ships independently and is reversible on its own. No phase requires the next
one to have landed.

### Phase 0 — Stop the bleeding (no architecture change)

Landable this week, independent of everything else.

- Turn the reaper live. It ships `DRY_RUN=true` with no CD path
  (`backend/charts/agent-vm-reaper/prod_agent_vm_reaper_cronjob.yaml:58`).
- Change `"diskSizeGb": "50"` (`backend/routers/desktop_agent_vm.py:169`) to 10. The
  database is 1–4 GB.
- Add the missing `DELETE /v2/agent/deprovision` and call it from sign-out and account
  deletion. Today nothing ever deletes a VM, so an account deletion leaves the user's
  entire screen history on a disk in GCP indefinitely — an erasure failure independent of
  any cost concern.

**Effect:** cuts the dominant cost line ~80% and closes a GDPR gap, with no migration risk.

### Phase 1 — Move the agent in-process (the real change)

Port the tool loop from `backend/agent_vm/main.py` into the macOS app (or a local sidecar).
The database is already local; the VM copy is redundant.

- Replace `execute_sql` with the same bounded, read-only accessors omi-v4 exposes.
- Replace the Python cosine full-scan (`agent_vm/main.py:409-425`) with `sqlite-vec` on the
  local `omi.db`. Strictly better than both the current design and v4's substring scan.
- Keep `backend/agent-proxy/` as a thin stateless proxy for managed-plan model calls and
  budgets. It already exists and does not change.

**Backwards compatibility:** ship behind `OMI_LOCAL_AGENT=1`, default off. Both paths
coexist; the client picks one at session start. No wire-format change.

### Phase 2 — Retire the sync path

`AgentSyncService` + `AgentVMService` (~1,000 lines of gzip/delta/backoff/re-upload
machinery) exist **only** because the data was moved somewhere it did not need to go. Once
Phase 1 is default-on, this is a net deletion.

### Phase 3 — Decommission

Delete `backend/routers/desktop_agent_vm.py`, the reaper, the chart, and the VM image
build. Only after Phase 1 has been default-on long enough that no client falls back.

---

## 5. Backwards compatibility and migration

**Clients in the field are the binding constraint.** A desktop build from before Phase 1
still calls `POST /v2/agent/provision` and expects a VM.

| Concern | Handling |
|---|---|
| Old clients | `/v2/agent/*` keeps working through Phase 3. Phase 3 gates on telemetry showing the old path unused, not on a date. |
| Data migration | **None required.** The authoritative copy is already local; the VM holds a derived copy. Deleting it loses nothing. This is the single biggest thing that makes this migration cheap. |
| In-flight sessions | Phase 1 is chosen at session start, never mid-session. |
| Rollback | Clear `OMI_LOCAL_AGENT` and the next session uses the VM again — until Phase 3, which is the one-way door. |
| Users whose VM is already gone | Already handled: `checkVMNeedsDatabase` re-uploads on an unreachable health check. Under Phase 1 this path stops existing. |

**Migration ordering rule:** Phase 3 is irreversible; Phases 0–2 are not. Do not start
Phase 3 until the old path has been idle for a full desktop release cycle.

---

## 6. If server-side access IS a shipped promise

Then replace per-user VMs with **one shared index**, not 300k rented machines:

- Screen-derived embeddings → a shared vector store with a server-side uid filter, exactly
  as omi-v4 does for memory claims (`worker-rs/src/routes_memory.rs:41`).
- Screen *frames* still never leave the device.
- The agent runs in a shared multi-tenant worker, holding no per-user state between turns.

Same principles, different storage tier. The per-user VM is not required by either answer
to §1 — the question only changes what replaces it.

---

## 7. Cost

At 300k users, us-central1 list price, 30% DAU at ~3h/day. INFERRED (public pricing, not
read from either repo).

| | Now, reaper disabled | Now, reaper live | Local-first |
|---|---|---|---|
| Per-user disk | $5.00/user/mo | ~$0.25/user/mo | **$0** |
| Per-user compute | ~$0.33/user/mo | ~$0.33/user/mo | **$0** |
| **300k total** | **~$1.6M/mo** | **~$250k/mo** | **~$3–15k/mo** shared |

Two caveats that decide whether this is real:

1. **Do not lift the 3-second sync cadence onto object storage.** At 300k users that is
   ~180 billion Class A operations/month — roughly **$810M**. The write path must become
   an event log first. This single detail is the difference between a 99% saving and a
   catastrophe.
2. **Model tokens dominate both sides** and are unchanged by this decision.

---

## 8. What is lost

1. **Server-side execution while the desktop is asleep.** Real, and the whole subject of
   §1.
2. **A fat box for batch jobs** (re-embedding a year of screenshots). Better solved by a
   shared job queue than by 300k idle VMs.
3. ~~Arbitrary-SQL agent flexibility~~ — a **gain**. `execute_sql` with an LLM on the other
   end, on a box holding the user's whole screen history behind a public IP, is a larger
   attack surface than v4's two approval-gated tools. See `SECURITY-AUDIT.md`.

Nothing about retrieval quality or latency is lost. In-process `sqlite-vec` over a local
disk beats an HTTP hop to an `e2-small` running a Python dot-product loop over 10,000 rows
on every query, on every axis.

---

## 9. Open questions

- **§1.** Blocks everything.
- Is `AGENT_VM_REAPER_LIVE=1` actually set in production? Not determinable from the repo,
  and it decides whether today's cost is ~$1.6M/mo or ~$250k/mo at scale.
- Measured `omi.db` size on a real install. The 1–4 GB estimate is the weakest input in §7.
- Does any non-desktop surface query screen history today, or is that capability
  incidental?
