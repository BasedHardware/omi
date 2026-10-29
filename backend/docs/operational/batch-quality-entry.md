# Batch quality entry and guard policy

Owner: batch rollout operator; lead approves entries and owns production writes.
David's 2026-10-29 ruling narrows batch rollback to T1 custody, T2 measured lost
speech and T4 language. T3 wedge age, held ratios, revision changes, configuration
drift, manifest/observer pins and manual markers are alerts. An alert cannot
create a rollback or become a replacement entry gate.

The in-cluster guard logs wedge/stuck-age alerts and retains custody/proven-loss
rollback. Its schema has no language evidence; the external observer retains T4.
Missing hard-three evidence is UNKNOWN, never clean and never a fabricated loss.

## Replacement external observer and caller

Deploying this PR does not switch an existing external process. The lead must
install these scripts into a fresh release directory, start a fresh read-only
observer process and verify a real aggregate, then switch the caller to the
single gate below. Keep the previous process until the hard-three successor is
verified. Stop it through its owning process manager after the handoff. Do not
edit a running script, its seal or its markers, and do not hand-archive markers.

The legacy C controller, two-phase reseal caller and marker-ready synchronization
are retired from the replacement route. Do not run both controllers as actuators.
Do not migrate their soft historical latches into the new entry gate.

The read-only collector is the installed paged batch metadata sampler
(`paged_sample.py`). It must provide complete custody, terminal/held speech and
language-route aggregates. The adapter loads its existing dependencies read-only,
then redirects its optional T2 marker lookup to a fresh empty task directory.
It does not consult `t2-window.json`, manifests, worker pins or old epochs.
It samples all admitted obligations in the actual observation window; no marker
can exclude historical custody. Sample-source failure becomes UNKNOWN.

From the repository root, with the authorized `ro-prod` agent tier selected:

```bash
python3 -I backend/scripts/rollout/batch_quality_observer.py \
  --sampler "$SAMPLER" --since "$OBSERVATION_START" --percent 0 --out "$OBSERVER_OUT"
```

Target a two-minute poll interval. Freshness and observed continuity permit at
most 300 seconds between samples, matching the census freshness limit.
`OBSERVATION_START` is the actual new-state
observation start, including partial-apply obligations. It is a measurement
boundary, not an arming permit. No guard qualifies until a full 30-minute new
state lookback has elapsed. Keep numeric-only `watch-samples.jsonl` and
`watch-latest.json`; read failures persist an UNKNOWN record. The scripts never
write production, change admission or authorize an entry. Existing authorized
hard-three rollback execution remains lead-owned until its successor is proven.

## One entry checklist

Before 5%, assemble a JSON packet with `serving_sha` (full commit) and these
receipts. Each owning lane must attest the evidence; the CLI validates the
contract, not the truth of a caller-supplied receipt.

| Receipt | Required evidence |
| --- | --- |
| `errclass` | `complete=true`, `serving_sha`, `at`, `evidence_ref`, `baseline_hours>=24`, `includes_zero_percent_traffic=true`, `untriaged_new_classes=0`. No count threshold may hide a new class. Include all batch traffic that continues at 0%. |
| `replay` | `complete=true`, `serving_sha`, `at`, `evidence_ref`, `verdict="PASS"`. State real corpus coverage, synthetic-only coverage and unsupported concurrency separately. Missing required coverage cannot be waived by changing the verdict string. |
| `observer` | The fresh `watch-latest.json` from the new observer, with measured T1/T2/T4 all CLEAN and at least 30 minutes of continuously observed CLEAN samples. The observer derives the start from actual collector readTimes; a supplied `observation_since` cannot backdate it. Gaps above 300 seconds or UNKNOWN reset continuity. Post-read wall time does not fill missing observation. No hard harm in `reasons`; soft alerts remain visible. |

Errclass/replay receipts expire after 15 minutes; observer evidence after five.
An expired receipt asks its owner to refresh evidence, never to reseal a packet.

```bash
python3 -I backend/scripts/rollout/batch_quality_gate.py "$GATE_PACKET"
```

Exit 0 and `READY_FOR_LEAD_ENTRY` mean send the evidence to the lead for
APPROVE ENTRY. They do not grant a write. Any other result keeps entry pending.
The lead's separate approval must name the reviewed packet and serving SHA.
No gate-C manifest, marker, observer hash or old latch id is required.

Before rollback, revert or blaming the latest change, query the same class on
the previous two serving revisions. Report counts, exposure and rates for all
three. A class predating the newest change is chronic; do not roll back that
change for it.

During each 30-minute soak, the batch owner posts structured PR holds for open
PRs affecting backend-integration, batch workers and shared projection/claim
dependencies, then unholds those exact PRs after the measured verdict. Revision
changes alert; they never cause automatic rollback.

## Runtime ramp migration

The persistent `_ramp` percent and its cache supersede env once seeded. An env
rollback cannot lower a populated remote percent. Before any positive remote
ramp, the lead must migrate every active rollback actuator and observer to the
same CAS writer/effective readback and verify zero under that control. Keep
admission at zero until that separate migration is complete. This PR does not
seed remote config or grant production writes.
