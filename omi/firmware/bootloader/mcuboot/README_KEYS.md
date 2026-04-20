# MCUBOOT Keys — Removed from repo

The bootloader private keys (`root-rsa-2048.pem`, `enc-rsa2048-priv.pem`)
previously lived in this directory. **They have been removed from the tree**
because they must not be committed.

## Why this matters

- `root-rsa-2048.pem` is the **firmware signing key**. Anyone holding it can
  produce firmware images that pass bootloader verification on deployed
  devices. That means an attacker can push malicious firmware to every Omi
  device, full post-auth — and then do anything the hardware can do (mic
  capture, flash persistence, network pivot).
- `enc-rsa2048-priv.pem` is the **image encryption key**. Anyone holding it
  can decrypt any encrypted firmware image shipped for these devices —
  firmware confidentiality is gone.

## What to do

1. **Rotate both keys.** Generate fresh RSA-2048 keys, store the private
   halves in a secure KMS (GCP KMS, AWS KMS, or a hardware HSM). The
   public halves stay checked into the tree alongside `mcuboot.conf`.
2. **Re-flash / sign-rotate deployed devices.** Ship a signed firmware
   update built with the new keys; devices that haven't received the
   rotation will still accept images signed by the compromised keys
   until they've been re-keyed.
3. **Scrub the old keys from git history.** The private keys landed in
   git history and any clone / fork still has them. Use `git filter-repo`
   to remove the blobs, force-push, and rotate any tags.
4. **Keep new keys out of the tree** — see `.gitignore` at this directory.

## Build instructions

CI / local builds should supply the signing key via environment:

```bash
# Dev builds (HSM-backed key export, gitignored)
cp /secure/kms-export/root-rsa-2048.pem omi/firmware/bootloader/mcuboot/
cp /secure/kms-export/enc-rsa2048-priv.pem omi/firmware/bootloader/mcuboot/
west build ...
```

Production builds should call the KMS directly instead of exporting the
private key to disk.
