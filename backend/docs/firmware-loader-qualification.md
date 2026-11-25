# Opt-in firmware loader qualification

The firmware metadata routes accept optional query parameter `bootloader_sha256`:
`GET /v2/firmware/latest`, `/stable`, and `/version`. It is an exact lowercase
64-character hexadecimal SHA-256 digest. The app must read fresh, supported UUID43
loader evidence from the connected device; omit the parameter when unknown. Do
not infer it from firmware version, update history, UID, or device serial.

A release can require qualification by adding this line inside its existing
`KEY_VALUE_START` / `KEY_VALUE_END` metadata block:

```text
required_bootloader_sha256:<qualified lowercase SHA-256>,<another qualified SHA-256>
```

The list is scoped to that individual release. Missing key preserves existing
eligibility. A present empty, malformed, or non-string list denies the release.
Guarded metadata must use a single metadata block with one `key:value` per
line and exactly one canonical guard declaration. Bare keys, `=` syntax,
multiline continuations, duplicate declarations, and misplaced guard declarations
fail closed rather than being dropped by the legacy parser. Metadata keys use
letters, digits, and underscores, beginning with a letter or underscore. Guard
detection recognizes the exact key token at logical line start (including after
the block opener); it does not infer arbitrary misspellings or Markdown-wrapped
keys. Review the literal release metadata before publication.
Whitespace around list elements is allowed; uppercase hashes are not. Missing,
malformed, or nonmatching client evidence denies a guarded release. Qualification
is necessary, not sufficient: existing blocked, audience, rollout, tag, publication,
and version rules still apply. Audience matches and explicit-version requests
cannot bypass qualification. Explicit-version requests otherwise retain their
existing rollout-percent bypass. Latest/stable may return an older release only
when it already satisfies the unchanged selection policy; otherwise the existing
404 response applies. Response fields are unchanged.

This is a compatibility guard, not attestation or authorization. Evidence is
client-supplied, and public GitHub asset URLs remain directly downloadable. It
does not identify the bootloader on old .21 firmware that cannot report UUID43,
repair a broken loader, qualify a rescue, or make an unguarded release safe.

## Rollout boundary

This change does not edit any release or deployment. Before enabling a guarded
candidate, separately verify its allowed loader hashes on hardware, review the
release metadata, and deploy the backend and app integration through normal
approval. Old clients omit evidence and cannot receive that guarded candidate.
A .25 app-only evidence addition cannot bootstrap unknown .21 devices into a
qualified cohort. Do not add hashes based only on successful daily driving.

## Local verification

`backend/tests/unit/test_firmware_bootloader.py` exercises real metadata parsing
and mocked GitHub reads for all three HTTP routes, malformed/missing/nonmatching
hashes, list policy, blocked and audience precedence, rollout retention, and
legacy fallback. Existing firmware rollout, pagination, specific-version, and
legacy-DFU tests provide regression coverage. These are mocked-server checks,
not live production or hardware qualification.
