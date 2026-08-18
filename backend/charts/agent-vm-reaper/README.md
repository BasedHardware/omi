# Agent VM reaper

Hourly CronJob that deletes aged idle/abandoned `omi-agent-*` GCE instances so
their ~50 GB `pd-balanced` boot disks stop billing.

## Why

Idle auto-stop leaves VMs in `TERMINATED`. Disk `autoDelete: true` only runs on
instance **delete**, not stop. Without a reaper, every user who ever opened the
desktop agent leaves a permanent disk (~$5/mo).

## Policy

| Target | Rule (defaults) |
|--------|-----------------|
| `TERMINATED` | `lastStopTimestamp` older than **12h** |
| `RUNNING` | **Never deleted here.** The fleet reconciler is the RUNNING authority: a healthy VM with no session lease past `AGENT_VM_IDLE_TEARDOWN_SECONDS` (default 30m) is **deleted** by the reconciler itself (disks reclaimed via `autoDelete`); this reaper covers TERMINATED leftovers the reconciler cannot reach (e.g. ownerless records). Do not reap RUNNING by creation age — that would delete live sessions (review #10390). |

After a TERMINATED VM is deleted, `GET /v2/agent/status` sees `NOT_FOUND`,
demotes the client-facing status to `updating`, and records
`reconcile.state=missing` (when no reconciler lease/quarantine owns the
pointer). Status never queues reconciler demand — waking a VM requires a real
session or an explicit ensure call. Desktop `ensureExistingOrProvision` can
claim a replacement immediately because missing pointers are replaceable; the
reconciler's grace/session clear remains the backstop when the request path
does not replace first.

## Apply (refuse-by-default)

There is no CD path for this chart today. Install manually after merge:

```bash
# 1) Install IAM + CronJob in dry-run (log-only)
AGENT_VM_REAPER_APPLY=1 bash backend/scripts/apply-agent-vm-reaper.sh

# 2) Kick a manual job and read logs
kubectl -n prod-omi-backend create job --from=cronjob/prod-agent-vm-reaper agent-vm-reaper-manual-$(date +%s)
kubectl -n prod-omi-backend logs -l job-name --tail=200   # or logs job/<name>

# 3) Enable deletes
AGENT_VM_REAPER_APPLY=1 AGENT_VM_REAPER_LIVE=1 bash backend/scripts/apply-agent-vm-reaper.sh
```

Local inventory (no deletes; lists by status, including RUNNING that the reconciler must stop first):

```bash
python3 backend/scripts/agent_vm_reaper.py --inventory
python3 backend/scripts/agent_vm_reaper.py --dry-run
```

Ownerless RUNNING VMs (no Firestore `users.agentVm.vmName`) are outside the reconciler and need operator cleanup. Join the inventory names against Firestore before any one-shot delete.

## Related

- Issue: https://github.com/BasedHardware/omi/issues/7326 (cost half)
- Script: `backend/scripts/agent_vm_reaper.py`
- Apply: `backend/scripts/apply-agent-vm-reaper.sh`
