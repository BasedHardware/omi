# Trusted owner confirmation boundary

These are required contracts, not implemented owner enrollment or target gateways.
The current host demo supplies public fixture-owner policy and explicit boot
outcomes. Its nonce/owner/hash ACK checks are simulated authority, not a secure
phone session or proof of actual application health.

Separate three facts:

1. Image signature verification authenticates exact bytes and a permitted image
   role against a trusted owner registry. It does not prove health, grant root
   privileges or enroll that signer. Published fixture keys have no real authority.
2. Enrollment/revocation is a separate trusted owner-presence/session operation,
   with recovery/lost-phone policy and replay resistance. A paired phone alone
   does not establish owner intent, and personal firmware must not edit registry,
   policy, reference metadata or protected recovery. No registry persistence or
   enrollment gateway is implemented here.
3. Trial health and confirmation concern only the admitted personal application.
   A Secure controller must bind ACK to owner session/role, current boot nonce,
   exact artifact digest, journal sequence, compatibility policy and fixed image
   role. Re-admission and final destination digest must still match. An app's
   `healthy` report is untrusted evidence; it cannot authorize arbitrary changes
   to recovery, supervisor, radio, keys, rollback policy or stored owner identity.

A trusted owner can intentionally confirm a bad personal app, and a malicious app
can lie about health. Therefore confirmation is not the sole safety mechanism:
protected return-to-stock must remain selectable independently of that app and
must never be overwritten through the personal image/copy/confirmation API.
Reference promotion must preserve at least one independently usable known-good
artifact across interruption; exhaustive target promotion durability is not proven.

Any future supervisor/radio/recovery update needs a distinct authenticated
maintenance role, compatibility and recovery protocol. Personal owner signatures
must not be accepted for those roles by reusing a generic confirm endpoint.
Owner autonomy for everyday app OTA does not require distributing maintainer
keys or trusting arbitrary app code with Secure flash/DMA/driver control.

Initial developer scope is app-only against a stable radio and protected services.
Paired-core development and legacy first-OTA bootstrap remain separate unresolved
engineering/migration work. No claim that existing shipped bootloaders accept a
new owner key or that this research provides a safe retrofit.
