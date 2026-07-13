# Dashboard Home policy

The redesigned Home is the canonical desktop dashboard. `legacyHome` remains
available only as a temporary recovery path while the redesigned experience
finishes its rollout.

## Legacy Home sunset

- Keep the Advanced Settings toggle for two stable desktop releases after this
  policy ships.
- During that window, use the toggle only to unblock users from a regression in
  redesigned Home. New dashboard work does not need a parallel legacy version.
- Remove `legacyHome`, `useLegacyHomeDesign`, and the toggle after the two-release
  window unless a documented accessibility or release-blocking regression still
  requires the fallback.
- If removal is deferred, record the blocking issue and a new review release in
  this document. Do not silently convert the fallback into a permanently
  supported second dashboard.

## Connector navigation

Apps is the canonical connector-management destination. Dashboard affordances
such as the inline **Connect** button are navigation shortcuts to Apps, not
separate connector browsers or setup flows.
