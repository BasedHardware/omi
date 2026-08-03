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
| `RUNNING` | `creationTimestamp` older than **2d** |

After a TERMINATED VM is deleted, `GET /v2/agent/status` sees `NOT_FOUND`,
clears Firestore `agentVm`, and the desktop client re-provisions + re-uploads
its DB (`AgentVMService`).

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

Local inventory dry-run (no cluster mutation):

```bash
python3 backend/scripts/agent_vm_reaper.py --dry-run
```

## Related

- Issue: https://github.com/BasedHardware/omi/issues/7326 (cost half)
- Script: `backend/scripts/agent_vm_reaper.py`
- Apply: `backend/scripts/apply-agent-vm-reaper.sh`
