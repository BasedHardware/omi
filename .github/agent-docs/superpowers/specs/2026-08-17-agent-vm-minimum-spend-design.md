# Agent VM minimum spend

- Date: 2026-08-17
- Status: Superseded by the full Cloud Agent VM retirement in PR #11795. Do not
  execute this minimum-spend prescription or its deleted reconciler workflow.
  The remaining live-infrastructure teardown is documented in
  `backend/docs/runbooks/cloud-agent-vm-infrastructure-retirement.md`.
- Decision owner: Agent runtime / cost policy
- Operator instruction: "Have Fable prescribe the best cost savings approach
  that gets us down to minimum spend … Be aggressive in savings, ok with
  degrading UX a little bit."

## Measured situation (2026-08-17)

Demand, from prod agent-proxy logs (`connecting to vm=` is emitted exactly once
per successful session):

- 761 successful sessions in 30 days across 41 distinct users.
- Six sessions in the last 7 days, all one user. **Zero since 2026-08-13.**
- Last 24h: 135 WebSocket attempts from 43 users, **zero** reached a VM
  (99 "not reachable", 90 "RUNNING but unhealthy, resetting", 36 "no VM").

Cost:

- Last closed 7 days: **$3,725/week** ($2,050 VM + $964 disk + $711 external
  IP) — a ~$16k/month run rate.
- The operator mass-stopped the RUNNING fleet (1,153 → 0) at 19:41 UTC. Stop
  does not delete disks: **1,208 pd-balanced disks / 60,400 GB ≈ $6,040/month
  (~$199/day) keep billing.** Disks are now the dominant cost.
- Within an hour, 10 VMs were RUNNING again via wake-on-open and reconciler
  restarts. Without code changes the stop is a one-shot, not a steady state.

Mechanism (confirmed, sibling evidence in the knowledge base): the 2026-08-04
Python cutover dropped the old guest's `sudo shutdown -h now` fallback on
service-account-less VMs, so VMs stopped dying. August cohort retention 97.6%
vs July ~22%. Creation was *lower* in August than July. Ownerless fraction: 0.

The root allocation error: the design pays `O(registered users × 24h)` for
demand that is `O(concurrent sessions × session length)` — a ~1,000× gap at
the July peak and an ∞ gap today.

## Prescription

**A VM (and its disks) may exist only around a session. Everything without
session demand is deleted, not stopped. New capacity is explicit opt-in.**

### Target steady state

| Line | Today (run rate) | Target | How |
| --- | ---: | ---: | --- |
| Disks (standing) | ~$6,040/mo | ~$0 | Operator deletes the stopped fleet; code deletes instead of stopping from then on (`autoDelete` reclaims both disks with the instance) |
| VM compute | ~$8,800/mo pre-stop | ~$0 standing | Provisioning dark in prod; undemanded VMs deleted ≤35 min after last session |
| External IPs | ~$3,050/mo pre-stop | ~$0 standing | IP billing follows VM-hours; dies with the fleet |
| **Total** | **~$16k/mo** | **≤ $25/mo** at current demand | Session-scaled residual only |

If July-peak demand ever returns (~50 sessions/day), the same code yields
roughly 50 × ~1.5 VM-hours/day ≈ $2–4/day ≈ **$60–120/month** — still ~100×
below the August run rate, with no further intervention.

### What UX is spent (quantified, per the operator's "a little")

1. **The feature goes dark in prod for new/returning users** until an operator
   sets `AGENT_VM_PROVISIONING_ENABLED=true`. Measured regression today:
   **zero** — no user has completed a session since Aug 13; the 43 users/day
   who try currently get an error anyway. When the flag is off they get an
   honest 503 instead of a broken spinner.
2. **Cold start replaces warm start.** A VM idle ≥30 min is deleted. The next
   session is a full provision (~2–5 min incl. readiness) plus desktop DB
   re-upload, instead of a ~60–90 s restart. Affected population at current
   demand: ~1 user.
3. **App launch/status polling no longer resurrects VMs.** Only a real session
   connect (agent-proxy) or an explicit ensure call wakes anything. A user who
   only opens the app never pays for a VM again.
4. **No state persists between sessions.** The state disk held only a
   client-uploaded SQLite copy (the guest literally errors "Upload omi.db
   first"); the Chrome profile has always been a tmpfs and never persisted.
   Deleting the disk loses nothing unique — it re-uploads on next session.

### Ranked actions — dollars saved per unit of risk, in execution order

#### Operator actions (live infrastructure; David authorizes and executes; NOT in this PR)

1. **Delete every `omi-agent-*` instance, then sweep orphaned `omi-agent-*`
   disks.** ~$6,040/month, effective immediately (~$199/day while deferred).
   Risk: destroys re-uploadable SQLite copies; there are zero in-flight
   sessions to kill. This is the single highest-value action and it is
   independent of any deploy. `autoDelete` is set, so instance delete cascades
   to disks; the disk sweep catches any orphans.
2. **Bake this PR on dev, then promote to prod** (desktop-backend +
   `agent-vm-reconciler` job via `desktop_backend_prod.yml`). This is what
   makes action 1 stick: without it, wake-on-open and drift-restarts regrow
   the fleet. Note the prod deploy also turns provisioning dark (the flag is
   deliberately absent from the prod workflow env).
3. **Optional backstop: install/flip the reaper live** (`DRY_RUN=false`,
   TERMINATED >12h). With the reconciler deleting undemanded VMs itself, the
   reaper only covers records the reconciler cannot reach; ownerless count is
   0 today. Low value, low risk — fine to skip.
4. **Decide the feature's future explicitly.** Zero successful sessions since
   Aug 13 is a *reliability* failure this prescription does not fix. Re-enable
   provisioning only when someone commits to fixing the runtime; a feature
   with zero working users should stay dark until then.

#### Code (this PR)

1. **Reconciler: undemanded ⇒ deleted.**
   - A stopped VM with no start demand, no session lease, and no active
     boot-image migration is deleted (identity-fenced by numeric instance ID),
     and its owner record is marked `missing` so provisioning can replace it
     instantly. This also auto-drains any future stopped pile.
   - Idle RUNNING VMs are deleted after `AGENT_VM_IDLE_TEARDOWN_SECONDS`
     (default lowered 1h → 30m, the floor) instead of stopped.
   - The drift path repairs-and-restarts **only on demand**; a drained drifted
     VM without demand is deleted in the same run. This retires the
     stop-rewrite-restart loop that was resurrecting broken guests ~90×/day.
   - Undemanded RUNNING VMs behind a `recreate_required` boot-image record are
     stopped so the next run deletes them, instead of billing forever behind a
     terminal marker.
2. **Wake-on-open removed.** `GET /v2/agent/status` (and the shared read
   decision used by tools status) is strictly read-only: it may demote a stale
   `ready` cache and record a provider 404, but never queues reconciler start
   demand. The agent-proxy connect path keeps `request_vm_start` — real
   sessions still wake stopped VMs.
3. **Provisioning dark by default.** `POST /v2/agent/provision` refuses to
   *create* (or replace a missing pointer) unless
   `AGENT_VM_PROVISIONING_ENABLED=true`; existing live owners keep the
   idempotent "exists" path so released desktops degrade gracefully (the
   desktop already logs-and-continues on provision failure). Dev sets the flag
   for dogfood; prod does not.

### Considered and rejected

- **Smaller machines / Spot / smaller or pd-standard disks.** These cut unit
  price; the actual cost lives in *lifetime*. After delete-on-idle, total
  fleet-hours ≈ session-hours and all of these save <$5/month combined — not
  worth the review or breakage risk (boot image size constraints, Spot
  preemption mid-session). Revisit only if sustained demand returns.
- **Public IP removal / proxy over `privateIp` (#7326).** Once VM-hours ≈ 0,
  the external-IP line follows to ≈ $0, so this is now a *security* item
  (bearer token over plaintext public HTTP), not a cost item. It needs Cloud
  NAT for guest egress plus an agent-proxy change; sequence it with any
  feature revival, not here.
- **Relying on #11755 idle-*stop* alone.** Stop preserves disks. At one VM per
  registered user that is the $6k/month disk line forever. Stop is the wrong
  terminal state for state that is a copy.
- **Waiting for the Cloud Run session runtime**
  (`feat/agent-vm-session-scaled-runtime`). That ADR reaches the same
  economics by replacing the runtime; this PR reaches them with ~200 net lines
  against the existing reconciler, and the branch is currently red and saves
  $0 until fully landed. **This prescription supersedes it in priority**: keep
  the ADR as the long-term shape *if* the feature earns users again; spend
  nothing more on it while demand is zero.

### Risks and honest caveats

- **Teardown is destructive by design.** Fences: owner lease + zero session
  leases + no start demand + numeric-instance-ID-fenced delete + idleSince
  persisted across ≥30 min of runs (for the idle path). The worst realistic
  failure is deleting a VM a user reconnects to minutes later — cost: one cold
  provision.
- **Reconciler-driven cleanup of a large stopped fleet is slow** (rollout
  cohort phasing, 5-min ticks). The operator mass-delete is the primary
  mechanism; the reconciler handles stragglers and the future.
- **Stale `missing` records linger up to the cleanup grace** (24h prod) and
  show as "updating" to status polls. Cosmetic; provision replaces them
  immediately on demand (when the flag allows).
- **A prod deploy of this PR changes prod behavior** (dark provisioning,
  deletion policy). That is intended and called out; the prod deploy itself
  remains a manually approved operator action.

### Sequencing after this PR

1. Operator actions 1–2 above (delete fleet; bake + promote).
2. If the feature is revived: fix the runtime (agent-vm-reliability track),
   re-enable the flag env-by-env, then take #7326 (private IP + Cloud NAT)
   and create-on-first-use in the desktop client as the next code cuts.
3. If it is not revived within a quarter: delete the feature surface
   (reconciler, reaper, charts, broker) rather than maintaining a zero-user
   control plane.
