# Corrected CV1 validation model — kit7

This supersedes earlier statements that a regenerated network public key is necessarily rejected by installed b0n. Product baseline: `e86cda5abb0ea7ff942ac1bcd07261140953812c`; Nordic nrf `7787b264984022cda64d9629278942053e6462a5`; MCUboot `12e5ee106034972b0f1074d6f2261b2b39d1501b`.

| Layer | Retained effective configuration | What it establishes |
|---|---|---|
| Application MCUboot | RSA, length2048, slot-zero validation enabled | RSA-PSS-2048/SHA-256 verification configured; pinned imgtool uses PSS salt32. No new cryptographic acceptance/rejection test performed. |
| Network b0n | `SB_VALIDATE_FW_HASH=y`, `SB_CRYPTO_NO_ECDSA_SECP256R1=y` | SHA-256 hash integrity validation, not ECDSA authentication against provisioned public keys. |
| Outer network OTA wrapper | App-core MCUboot multi-image update configured; Nordic Kconfig explicitly expects app-core signature validation | Distinct from b0n validation. End-to-end negative signature/update-order tests still needed. |

`../tools/cv1/preflight-evidence/validation-excerpts/` contains exact line-numbered configuration excerpts and the relevant source branches. Nordic `nrf/subsys/bootloader/bl_validation/Kconfig:64–75` labels the hash mode “not secure” and explains the app-core signature role. `bl_validation.c:273–298` hashes firmware against its metadata; its dispatch selects this branch at lines417–423. The signature branch is separately conditional. ECDSA format flags, generated signatures and provision records do not mean that branch is enabled.

## Installed-image provenance and limits

`../tools/cv1/preflight-evidence/validation-evidence.json` records hashes of retained configuration, exact retained b0n/MCUboot HEX and historical installed readbacks. Every defined b0n and MCUboot image byte matched its corresponding saved readback. Every defined full-network bundle byte also matched. Those comparisons tie the retained build artifacts to saved installed images; configuration alone was not treated as proof. Source/build association is retained build provenance, not a new reproducible rebuild or fresh hardware observation. No raw memory is included in this kit.

Public network fingerprints remain useful provenance: baseline `f681aa213503faec007bee001252e461c1357bcafd72794333eab785e464f808`; later candidate `76d48548dbdbf2e645db20cb2a35aa77fe0aa416a425487cca75968fc90004dd`. Baseline metadata matches provision records; candidate metadata differs. `trust-comparison.json` now uses `matches_installed_provision_metadata`, not `trusted`. Neither comparison proves cryptographic acceptance/rejection in hash-only mode. It also does not prove outer MCUboot acceptance.

## Offline gates after correction

Preflight still rejects wrong board, changed artifacts, layout mismatch, unsupported/ambiguous roles, missing installed evidence, unknown validation modes, unreviewed app bytes and new network/full bytes. Exact reviewed baseline restoration remains the only full/network allowlist path to a later identity gate. Hash-only metadata differences are reported separately, without a false signature-rejection error. A hypothetical authenticated network validation contract must additionally match installed public trust metadata, but this tool still does not verify signatures.

The mode record requires externally pinned config/source/installed-image evidence. It is an attestation under the reviewed-contract model, not self-authenticating provenance. Never substitute a candidate contract, weaken gates or rewrite provision to obtain eligibility. OTA always remains unqualified; all hardware/release authority flags remain false.

Application RSA-PSS verification is reported separately with `image_signature_verification_performed=false`. Regression tests exercise the mode distinction and fail-closed decisions using synthetic artifacts; they are not cryptographic image verification tests.

## Key custody and phone trust

The app key source is a tracked repository PEM path selected by product `omi/firmware/omi/sysbuild.conf`; only path existence was checked, never private bytes. This does not establish a production secret or custody. Network build defaults generate development-key material in a fresh build directory; SDK warns against production use. No inference is made about shipped devices or the erased factory application.

SMP transport has plain GATT read/write permissions in this baseline; encryption/authenticated SMP permissions are off. Pairing availability does not establish paired-only OTA authorization and does not replace boot signatures. A low-cost stable local/offline maintainer signer is a proposal; KMS can follow later. No new key has been created, and existing devices cannot be assumed to trust a new key without a migration design.

Recovery without opening/SWD and everyday-user personal OTA are required. Official contributor checks and owner-authorized personal firmware are separate lanes. Neither distributing the maintainer private key nor requiring a jig for end users satisfies that design. See ota-development.md for staged owner enrollment, protected return-to-stock and migration limits. Trial-boot revert alone is insufficient if a custom app self-confirms, breaks radio or corrupts shared state.
