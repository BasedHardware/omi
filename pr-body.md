## Retire the cloud Agent VM: tombstone the broker endpoints and delete the control plane

Analysis of record: **SCA-339** (passive agent surface), **SCA-340** (migration mechanics), **SCA-341** (constraints/entitlements/privacy). Operator authorization 2026-08-17: "have the same omp agent open a PR for the deletion and retirement." Follows merged #11761 (minimum-spend freeze: opt-in provisioning, read-only status, reconciler deletes undemanded VMs).

### The measured case

- 1,179 → **48 GCE instances** (1,131 deleted 2026-08-17; the 48 stopped survivors are deliberately kept pending an export-window decision).
- **~$5,800/mo reclaimed** at the July peak (~$240/mo remains while the 48 stopped instances are held).
- **2,773 lifetime sessions across 106 users; zero successful sessions since 2026-08-13**; ~0.1% utilization at the July peak (41 distinct users/30d).

### Why this is route-and-delete, not a rewrite

The VM never defined its own integration tools: `agent_vm/main.py` fetched tool definitions from `GET /v1/agent/tools` and executed them via `POST /v1/agent/execute-tool` — the same endpoints the managed `omi:auto:chat-agent` path uses. **Those two endpoints stay.** Mobile chat never used a VM (the only mobile door was the default-off `claudeAgentEnabled` dev flag, removed here); desktop chat runs through `/v2/chat/completions` + the local agent runtime. Only the per-user GCE capacity and its control plane die.

### What is lost with no equivalent

- Cloud browser automation (Playwright on the VM).
- Cloud-resident general compute (Bash/workspace on a server filesystem) for users without the desktop app.
- Ad-hoc cross-table read-only SQL over synced desktop data (per-domain tools remain).
- Phone access to desktop-synced screen data (screenshot semantic search, daily recaps from the phone).

Demand for all four was the long tail (peak 41 users/30d, zero sessions since 2026-08-13).

### Security improvement

The VM path uploaded a **plaintext SQLite replica of desktop data to a per-user GCE disk**, and the proxy forwarded the user's **Firebase token over plaintext HTTP** (`ws://<ip>:8080/ws?token=…`) to a box running the Claude Agent SDK with `permission_mode="bypassPermissions"` and Bash. Deleting the fleet removes that entire exposure class; managed inference already runs in the encrypted-at-rest Firestore trust domain every other Omi feature uses.

### The client contract (the only change that hits every old client at once)

Old desktop clients (Stable 0.12.144 / Beta 0.12.186) keep calling the broker until they update, so the two desktop endpoints become **permanent tombstones**, pinned by contract tests (`backend/tests/unit/test_desktop_agent_vm.py`):

- `POST /v2/agent/provision` → **410**. Never 401 — `APIClient` has `signOutOn401: true` and a retirement must not force sign-outs.
- `GET /v2/agent/status` → **200 with a `null` body**. Never `200` + `status:"provisioning"` without an IP — old clients would poll 75×5s (~6.25 min).
- `POST /v2/agent/vm/stop-self` → 410 (only the deleted guest image ever called it).
- `GET/POST /v1/agent/vm-status|vm-ensure|keepalive` → **removed outright** (zero desktop callers; generated Swift only; mobile callers removed in this same PR). Recorded in `DELIBERATELY_REMOVED_ENDPOINTS` in `check_app_client_openapi_compatibility.py` so the app-client compatibility gate still rejects every *accidental* removal.

**Mobile ordering question, resolved:** deleting the code is not tearing down the running service. The GKE agent-proxy keeps serving its last image until the operator decommissions it (runbook below), so builds with `claudeAgentEnabled=true` are no worse off than today — they are *already* broken against a fleet with zero running VMs. Removing the toggle starts the clock on aging them out.

### INV-DATA-1 (named because this touches `app/lib/env/env.dart`)

The invariant's routing table pinned `wss://agent.omi.me/v1/agent/ws` as canonical Flutter agent routing, `env.dart` threw at startup if prod didn't match, and `env_test.dart:121,126` asserted it. This PR removes the retired surface from the routing table, the startup guard, and the guard tests in the same change — routing authority now covers only the surfaces that still exist. No other INV-DATA-1 row changes.

### What is deleted

`backend/agent-proxy/` (the GKE WS bridge), `backend/agent_vm/` (guest image), `backend/jobs/agent_vm_reconciler.py`, `backend/services/agent_vm_{lifecycle,migration_control,read}.py`, `backend/routers/desktop_agent_vm.py`'s 900-line broker (replaced by the ~50-line tombstone module), the 15 `backend/scripts/` agent-vm scripts, the `agent-proxy` / `agent-vm-firewall` / `agent-vm-reaper` charts, both `gcp_backend_agent_proxy*.yml` workflows, the Agent VM image build + reconciler deploy + release-pointer promotion steps in `desktop_backend_{prod,auto_dev}.yml` (plus their `AGENT_VM_*`/`GCE_*` service env vars, now explicitly `--remove-env-vars`'d), ~20 dead test files, the 6 agent-vm failure-class JSONs, and the docs/runbooks that died with it.

**Deliberately kept:** `/v1/agent/tools` + `/v1/agent/execute-tool` (passive agent tool surface), `agent_vm_account_cleanup.py` and the account-deletion purge path (48 VMs still hold plaintext user data — deleting them is a live privacy obligation until the fleet is gone), and the entire desktop-local agent runtime (`INV-AGENT-*`, `INV-CHAT-1` — the surface that actually delivers Architect's sold "Automations and vibe coding"; Windows sells Architect with no cloud VM ever).

### Operator runbook (out of scope for this PR — gcloud work, in order)

1. **Cloud Scheduler:** pause then delete job `agent-vm-reconciler-5m` (both projects if dev runs one).
2. **Cloud Run:** delete job `agent-vm-reconciler` (it rides the desktop-backend image; nothing in this PR deploys it anymore).
3. **GKE:** delete the agent-proxy Deployment/Service/Ingress/Helm release and the reaper CronJob `prod-agent-vm-reaper` (namespace `prod-omi-backend`), then remove the `agent.omi.me` DNS record.
4. **Firewall:** delete rules `omi-agent-vm-allow-private-8080` and `omi-agent-vm-deny-public-8080` (target tag `omi-agent-vm`).
5. **IAM:** delete custom roles `omiAgentVmReconciler`, `omiAgentVmReconcilerOperations`, `omiAgentVmReconcilerSubnetwork`, `omiAgentVmSelfStop`; delete service accounts `agent-vm-reconciler@`, `omi-agent-vm-bootstrap@`, `agent-vm-reaper@` and their bindings (incl. KSA `prod-agent-vm-reaper-sa` Workload Identity binding).
6. **GCS:** delete `gs://$AGENT_GCS_BUCKET/agent-vm/releases/**` (release pointers/startup manifests).
7. **Compute image family:** delete the `omi-agent` image family.
8. **The 48 stopped instances** (`omi-agent-*`, ~2,400 GB disks): **irreversible** — decide the export window first. Their workspace files have no download endpoint; the only export paths are (a) restart an instance on request and drive a live session, or (b) snapshot the disk to GCS and hand over a link. Holding them stopped costs ~$240/mo.
9. **Later, scripted (tracked as a follow-up issue):** Firestore sweep of `users.agentVm.*`, `users/{uid}/agentVmMigrations`, `account_deletions.late_agent_vm_cleanup`, and the `agent_vm_reconciler_leases` collection — only after the fleet is empty; then retire `agent_vm_account_cleanup.py`.

Rollback for steps 1–3 is the prior Cloud Run revision / re-applying the charts from git history (minutes). The tombstone endpoints themselves need no rollback — they are additive responses on paths old clients already tolerate.

### Rollback for this PR

Prior Cloud Run revision of desktop-backend, minutes (env flips are per-revision). The PR itself reverts cleanly: the deleted surfaces have no remaining callers.

### Out of scope (tracked as stage-3 issues under the parent)

Desktop client removal of `AgentVMService`/`AgentSyncService` (~1.76k LOC, rides the desktop release train); the Firestore sweep; the account-cleanup retirement; the infra teardown above.
