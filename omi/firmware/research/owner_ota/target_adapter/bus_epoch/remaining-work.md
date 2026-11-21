# Consolidated remaining work

This source/build stage does not remove ENOTSUP. It closes bounded arbitration
and reset-token policy gaps; more host-model layers would not prove the remaining
physical ownership and recovery guarantees.

| Work | Local engineering still possible | Controlled hardware evidence needed |
|---|---|---|
| Shared SPI3 ownership | Pinned-driver hooks proving whole NOR/SD completion, CS release, DMA stop and cancellation; a single Secure proxy for **all** clients. Disable/remove NS raw driver exposure in reviewed source/config. | SPU/GPIO/driver readback, real NOR+SD contention, timeout/fault behavior and no later DMA writes. CS snapshots alone cannot qualify. |
| Fixed storage services | Integrate reviewed actual NVMC/NOR execution backends and exact authenticated source/destination ranges; keep writes denied until reviewed. | Read/write/erase behavior, corruption detection, hardware endurance/latency and power interruption within approved disposable regions. |
| Boot epoch | Assign an additional protected 8 KiB ledger, entropy/provenance source and boot-before-service ordering; wear budget and factory/recovery lifecycle. No blind erasure/reseed. | Real commit/readback ordering, reset/power-cut and retention behavior; demonstrate old handles never regain access. Host cut tests do not prove this. |
| Secure/NS runtime | Real scheduler/gateway, DMA-safe ownership and memory bounds, stack/heap accounting, trusted owner session and health contracts. | SPU/SAU/IDAU attribution, peripheral master access, interrupt/handoff behavior and measured worst-case stacks. |
| Everyday owner OTA | Real transport integration, enrollment/revocation/lost-phone path, trial confirmation and independent protected return-to-stock. | Known RF peer; phone upload, failed app/BLE and independent recovery without opening device/SWD. |
| Legacy first transition | Complete boot-chain/partition/trust migration design; current loader power-cut hazard remains unresolved. | Reviewed migration trial and interruption testing. No current universally safe jig-free retrofit claim. |

## Existing owner-only batch; no new physical request

- RF verification peer/access: authorize a concrete additional receiver only when
  needed, or perform the already-batched close-range physical check. No access to
  the visible-but-unauthorized laptop is inferred.
- Qualified remote power/reset fixture: exact electrical/backfeed design and any
  purchase/installation need approval; no speculative purchase has been made.
- Bootloader/trust/keys/protection/layout migration: approve the eventual reviewed
  implementation, key custody/provisioning/migration and irreversible scope.
  The no-SWD recovery requirement is already agreed; do not ask it again.
  No key creation/import, root signing or protection activation is authorized by
  this local slice. Source algorithms are agent-owned work, not permission gaps.
- First legacy OTA transition: acknowledge/resolve the currently unproven
  interruption-safe bootstrap before any deployment. Maximum-version shortcut
  remains held, not a chosen policy.
- Restricted updater/native source and Library save approvals remain as previously
  batched; no alternate fetch/upload route was attempted. No extra access needed
  to complete this local slice.

Before a hardware trial, parent must lift its current hold for the exact external
CV1 identity, immutable artifact hashes, operations and fixed write ranges,
protection effects, reset/power sequence, potential data loss, and verified restore
plan. Reuse existing bench authorization where it covers that concrete plan;
source-only compilation does not activate hooks. Key/trust/bootloader/permanent
protection and electrical changes need explicit approval. There is no request to
physically act now and no target or upload action is pending from this stage.
