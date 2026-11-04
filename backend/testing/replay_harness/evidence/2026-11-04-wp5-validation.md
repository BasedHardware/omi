# WP5 replay gate validation — 2026-11-04

Host: m5-mbp. Branch: `replay-gate`, product base `7c95d10bea1a626737ee1225d53edb6bbdcc7e7f`.
No production access or GCP tier was used. No product or `.github` files were changed.

- [REF=BASE receipt](2026-11-04-wp5-ref-equals-base.gate.md): all 24 in-Git cases PASS,
  zero fixed/regressed cases, three contention repetitions per side, zero new exception class/sites.
- [Synthetic fixed receipt](2026-11-04-wp5-synthetic-fixed.gate.md): external Tier C case,
  one declared target fixed, PASS, zero new exception class/sites. A throwaway local clone
  supplied an unpushed product-only commit that bypassed producer custody. This proves product
  source selection and differential classification, not correctness of that synthetic bypass.
  Manifest ID/free text and transcript canaries did not reach either report or stdout.
- `make replay-gate REF=HEAD BASE=HEAD CASES=backend/testing/replay_harness/fixtures/admission-control`
  (with a private OUTPUT) also passed within the same emulator session as the first proof suite.

The runner used Java 21 and `node_modules/.bin/firebase emulators:exec --only firestore
--project demo-omi-isolated-tests`. The CLI's download of its pinned jar stalled; the successful
runs used its supported `FIRESTORE_EMULATOR_BINARY_PATH` override pointing to the host's cached
`cloud-firestore-emulator-v1.22.0.jar`. Both emulator launches shut down cleanly.

Final focused unit command (through `/Users/dazheng/workspace/omi/bin/omi-heavy run --`):

```bash
env BACKEND_FAST_UNIT_WARN_SECONDS=1.00 BACKEND_FAST_UNIT_FAIL_SECONDS=1.00 \
  backend/.venv/bin/python -m pytest \
  backend/tests/unit/test_replay_harness_gate.py \
  backend/tests/unit/test_replay_harness.py \
  backend/tests/unit/test_replay_harness_titling.py \
  backend/tests/unit/test_replay_harness_capture.py \
  backend/tests/unit/test_batch_replay.py \
  backend/tests/unit/test_batch_replay_result_transactions.py -q
```

Result: **247 passed**, with an existing Python `audioop` deprecation warning.
The gate suite itself has 37 fast tests, including snapshot cleanup, fixed adapter imports,
classification/verdict tables, manifest validation, corpus identity, and privacy.

Emulator integration: **2 passed** (all-fixture identity plus synthetic fix); the strengthened
synthetic transcript/stdout privacy proof was rerun independently and **1 passed**.
Commands unset `GOOGLE_APPLICATION_CREDENTIALS`, `CLOUDSDK_CONFIG`, and
`CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE` first. Real captured-owner inputs were not accessed.

Fixed adapter SHA256: `769c3b17a7fb284c66627d9f1cd20b628e95049a2740b2b0a580b37c01733765`.

Full private reports remain at `/Volumes/Ephemeral/scratch/replay-gate-wp5-evidence/{identical,synthetic-fixed}/gate.json`. Their identities and per-case corpus hashes are recorded here without case content.

## identical report identity

Report SHA256: `75c88d9374fc04343aa76caba5bd7612e3f8725f3b100eb401c2f6c1b2db1ea1`.

| case id sha256 | manifest + corpus + seeds sha256 |
|---|---|
| b2ea40e6178e664303d8a1461532359d0684bdb4da702037dc20b9e57f89056a | c7a5f07efab6bd3eb43aa1b211dee118a66208f65469bf9064b476f8c42d83ee |
| 5d6dd424b7f0f97898b2a9a9d5180acb4c868deed43f4d0e2dab05b20528ba55 | 1d4a45aa02b23cb80e05ec2734e6b1a86964c28ecda5a54209ef8409ad5142d1 |
| a98d4977a41b38cba0f24a6a09ccb7721715dd76557b402fa1b5311d2e2133b7 | ead3c33260226f39367f604246a52144350148a2a4eef9636181d9655f64adb8 |
| a81676b0db0cd6c589cda4858175f68a88397bf1252ad7bae1ced657e6d8fb50 | c8f499ddb21a0ab4d59982cc8cc3d1fe6df39fd15ea30a8bb817a449d50b2855 |
| ddaa0fade085ac5bab4012c041b2ff337fd40464b4967022fe7d3e8269b1fda0 | fd6a30b9c63cae4af40d965795a228a4c7394707f479f6a834e61936921eea91 |
| 05231ab8b255d552cdc5ee628f8c08a5bc390ccc38638579d3ed221af1a3c9c7 | e58a973d050ee47e98a2258ac75971e182a1c8d342c0a525c9429b2ebd0a4133 |
| 3226f70c91386f80b07110877d3c4b1115e874d58b45929c5544abd38800cece | ead3e6c5b79e7260a2d2930458f8e5ead4207000b9051923114b87fe3485197d |
| 934f6884b95ee0125f2fa59df0a3c0fe8b9418ec60ece4de8b4d792c298ab378 | 4a8597710637a9ddc81f78d39ac037aba741a663f2cf99fdf3294435170141b0 |
| 3617e07f0ff2be9be8fa16dfd6936be22574870ec77d545e84a053e6177dda2b | c54b36596071944723ff7a5075e8651baf5dd4cd5a5b59adb5dd771967ad9d87 |
| c8e5a500114527e4fea789bd68ec05d6aa27bbe562d5ccf6d3d1fe0830807af5 | a223b519d788ddc20573acc6614242d127870de432235ed6ab0cd0548cf81f96 |
| 857a0632a277a4e289fda334683b102ce53af853956bb25577219b27ec36a534 | 6f7aae80893788113bc3740653dd11d31a23d4ba399e252046bb591310ec8cc6 |
| 6b52665c2e22c9c6e244a71e0eb1924e4f0430340330e1e1b46216d54b9fe641 | f252b5fcd782e47c7a8311c9f6d9491be19ddb12ab30aeef728226bc137a9167 |
| 998da3e6774d7c7f1bc633be511d2d5298e33cd23c6c1e3b3d957a791b95070e | d70d0debefa9bcf7be3a3c061266ce98ddf3c5016d0f3514209b5604c30cb2f7 |
| f47fe157accd6aa893fba6023c7367cbaebd6d56c41d1ddbf64776aa012e697f | 9d6afceca60b93a484e39b4f8ce405b01478e793cac88a4d6fd656950eeca5fd |
| 2cea871d4f1f4cb279da24e724faccd03a14213d259f8a91fa6c19d45cfa0dea | 09c2c2f3098808a635c6942a830f626ba6676b0ee4442f112d843740163928f4 |
| c8163cb6e47445e3a02633930aea4f02547613c29a4d2bf324aeebb6aa07aa96 | c3b89f61d1d4316b1bd9431efcf54d80b3078932fdc2588b4d18dad87aaf8a30 |
| 45837f9e003752e8107574fffc6ff1205b9ff0350a91c1ffbe61bc90582f7f4b | 4d67ad24cfb1bf13b66820af9a4f2b9b50438e73594e4b5429688e02d951abea |
| 993dc602d560f59cfa2a50deeb8404a867692abee22b4e62952f34a97e9a3dba | 361560eb427da0f25c18f37bceb507a597277be62f5f1e7b662346633f810c71 |
| 8b73e3bc34af77d68b0fdd66a7271b8e1f93cf8e33faa96cfd17ff91e4852074 | d543b84fa076c4c1f604ea36c08dd8c6addd54091779ccb9b81a4dfcb52e6391 |
| 0b0016981eadfcae287dcd93df996dca4e5df59fdf6b7cd2c237966c4e033059 | 9665fb641b387f011af1907c704690a5a33fa3c7fbf608f16490aa0bcac0b6e2 |
| d39cf612c2d087ea709f5c9dd7b53d4fde41e2c9e62171d6d11bb1ed2ced9447 | 27e61e7c65fa9128908807987af5f08e5d03ba0be286b3d30fb861815baa0a2f |
| ab221062b035ae6980dce10327a499a978d55f4bab9043da4462c22f3facbf83 | 0a997b9e528cdefadffeede254e6997299786a9cf3961373be8f56ddccca368a |
| 740cf6656fcbcbd1914ee4bfccb8b68fa14453679d3ee28cb025cf3d0b46057a | 781303c5c027c45ef10390c2998bfaf86bc56817c57ea28f66af8f2a3b3279f6 |
| c40a9b082d69244b48bd32cea1814828bb5f959fc2a0bafa24e8abfbcb215c41 | 98cd0a04d110099e9a721878e159995f7e1d80639abac25f2ce3efc53abece00 |

## synthetic-fixed report identity

Report SHA256: `3b0b00f8533d54a6d405bf986589f5405db2b8d827beccabb82c9381b9f544fe`.

| case id sha256 | manifest + corpus + seeds sha256 |
|---|---|
| fba08db8477eb3d831d6584072f5f0be371b08fc4ec89671b0b443189b6a3b80 | ee03d4205e7357f7e3622a11658ec437c65b9e1a14bb026339f7c8cb9a8a49fe |

## Preflight and coordination limits

`omi-heavy run -- make preflight` ran all selected checks. It failed only in
`scripts/dev-harness/tests/spine/test_live_session.py::test_failed_reload_never_advances_loaded_identity[wedge-blocked]`:
the 0.2-second fake-daemon deadline expired before the transcript contained `app.restart`
(expected one call, observed zero). The dev-harness suite reported 573 passed,
7 skipped, 20 xfailed, and this one failure. Its source and implementation have no
changes from the product base in this task. The exact failing case passed on a focused
rerun (1 passed), and its entire test file then passed (40 passed). A broad preflight
PASS is not claimed.

ANX outcome recording was attempted using the `anx-participant` workflow. Both default
routing and explicit `--workspace omi` returned `workspace_unavailable` (HTTP 404,
`write_sent=false`); no card or note was written. These repository evidence files are
the durable handoff until ANX workspace routing is repaired.
