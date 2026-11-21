# Owner OTA host acceptance demo

This is a small LOCAL host demo, not firmware, BLE, a CPU emulator or deployment.
It compiles the actual shared C streaming verifier, PSA adapter, journal, copy and
boot-authorization services. A single C driver supplies in-memory NOR, a 137-byte
transport stub, fixture-owner ACKs and explicit HEALTHY/FAULT boot outcomes.
Python only builds/signs public test fixtures, launches C and checks its report;
it does not implement the OTA policy. No serial/debugger/device path or service.

## Run without a jig

Prerequisites: existing C11 compiler with UBSan, ARM Cortex-M compiler (or a supplied
NS ELF), Python with cryptography 43+ and pyelftools, NCS 2.9.0 source, and a native
PIC MbedTLS PSA archive built from its module. No installer/fetch runs. Missing
prerequisites fail explicitly. No signing service, key credential or account needed.

From the monorepo root, choose a NEW output directory outside ANY Git checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omi/firmware/research/owner_ota/host/run.py \
  --output /tmp/cv1-owner-demo-UNIQUE \
  --ncs /path/to/ncs \
  --mbedcrypto /path/to/native/library/libmbedcrypto.a \
  --arm-cc /opt/nordic/ncs/toolchains/b8efef2ad5/opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc
```

In the Omi workspace, agents route this command through `bin/omi-heavy run --wait 30`.
The default builds host/user_app.c with user_app.ld into an unsigned NS fixture
ELF. Edit that tiny app to represent a user build, or pass `--payload-elf /path/to/
existingNS.elf` instead of `--arm-cc`. Only flash PT_LOAD bytes within 0x54200..0xB4000
are signed into host fixtures; nothing is flashed or executed on a target.
Fixture variants append bytes, but that does NOT establish CPU health/fault:
the driver explicitly injects boot outcomes.

If a native archive is absent, build it explicitly outside Git with existing
CMake/Ninja and host compiler; this is optional setup, never silently run:

```sh
cmake -S "$CV1_NCS_ROOT/modules/crypto/mbedtls" -B "$CV1_NATIVE_BUILD" -GNinja \
  -DENABLE_TESTING=OFF -DENABLE_PROGRAMS=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
  -DCMAKE_C_COMPILER=cc \
  -DCMAKE_C_FLAGS="-I$CV1_NCS_ROOT/modules/crypto/mbedtls/include/library"
cmake --build "$CV1_NATIVE_BUILD" --target mbedcrypto -- -j4
```

The SDK internal include path is required by this pinned fork. No SDK edits,
install target, new key or download. Use trusted source/toolchain; this is not a
sandbox for arbitrary build scripts. Software MbedTLS PSA is not target Oberon.

## Demonstrated C path

1. User fixture A uploads in bounded chunks, is authenticated by actual PSA,
   copied/read back, and receives mirrored TRIAL intent before a boot token.
2. Simulated healthy outcome plus explicit fixture-owner ACK confirms A. Wrong
   owner, stale nonce or wrong digest ACKs reject. Registry is fixture input only,
   reinjected in RAM after restart; no persistent owner enrollment.
3. Build B follows the same path and becomes the confirmed reference. Uploads
   during pending/durable trial are blocked. Confirmation re-admits the external
   artifact and checks personal bytes before reference promotion; forced bank
   corruption cannot be confirmed.
4. Wrong-owner, modified-image and validly-signed wrong ABI uploads reject before
   modifying active personal bytes. Known-good remains protected.
5. Validly-signed candidate C receives a simulated FAULT, cannot be confirmed,
   and restart restores the known-good B through actual PSA/copy/boot services.
6. Partial upload/restart rejects incomplete data and requires retransmission.
   A completed VERIFIED-but-unstarted copy, an interrupted internal copy and an
   unconfirmed TRIAL restart all restore B; no partial image is authorized.
7. Root/legacy guards and all simulated user bytes are unchanged at the end.

Model restart resets volatile upload/lease/ACK state while retaining byte arrays.
It is not a host-process restart, real power cut, analog-cell model or scheduler.
The prior journal fault suite is separate; this acceptance sequence is not an
exhaustive promotion/interleaving proof. Both-invalid metadata/confirmed-reference
loss fails closed; repair/session protocols remain unimplemented.

## Exact simulated storage bounds

| Region | Range | Access |
|---|---|---|
| Trial journal | internal 0xF0000–0xF2000|Shared dual-page journal codec|
| Confirmed-reference journal | internal 0xF2000–0xF4000|Same codec, separate fixed view; no personal access|
| Personal container | internal 0x54000–0xF0000|Shared copy service only|
| User-data/gap/tail guards | internal 0xF4000–0x100000|Read/hash only|
| Root/owner-region guard | internal 0–0x54000|Read/hash only|
| External source banks |0x130000–0x190000,0x190000–0x1F0000|Upload only non-reference bank; lease blocks writers|
| Legacy external guard |0–0x130000|Read/hash only|

Internal program uses 4 B 1→0 units; erase uses 4 KiB pages/monotonic erase words.
External upload is a byte-granular NOR transport model. Fixed backend views and
bounds are code-selected, never manifest addresses. Confirmation changes the
reference journal instead of overwriting the old bank. The known-good bank must
still authenticate against its recorded hash. All isolation callbacks here are
explicit host stubs, not evidence of physical SPU/SPI protection. The full 3 MiB
flash arrays are HOST storage representation, not target RAM allocations.

## Test keys, format and evidence

Only published NONSECRET NIST CAVS 11.2 P256 keys in the pinned SDK signing tests
are used by host/fixtures.py. Producer pins source SHA and validates public points;
no arbitrary key-path option, private PEM, credential/enrollment or production key.
Do not enroll these known-compromised keys on a device or use for releases.

Signed bytes: SHA256 once over the 17-byte NUL-terminated domain `CV1-OWNER-APP-v2` plus the 128-byte header;
producer uses Prehashed SHA256 and verifier actual PSA verify_hash, raw r32 || s32 big-endian.
Header binds board/ABI/network fixture/generation/length/payload hash/key fingerprint.
These are research protocol/test-policy values, not installed-radio attestation.
Generated .cv1test files/public registry/ELFs/logs stay outside Git and local-only.
No real supervisor/release signing. Research/demo artifacts are excluded from
admission; no workflow can sign/publish/deploy through this program.

Inspect report.json and 03-host-demo.json: C exit/stdout/stderr, event-level artifact
hashes, exact source inputs, ELF/fixture/native archive/executable hashes, and explicit
simulation labels. Deterministic model decisions do not promise bit-identical
host/compiler debug metadata. A terminal PASS means only the stated host contract.

Acceptance tests use the same runnable entrypoint; missing configured dependencies
are explicitly SKIPPED, not a passed hardware stage:

```sh
CV1_DEMO_NCS_ROOT=/path/to/ncs CV1_DEMO_MBEDCRYPTO=/path/to/libmbedcrypto.a \
CV1_DEMO_ARM_CC=/path/to/arm-zephyr-eabi-gcc PYTHONDONTWRITEBYTECODE=1 \
python3 -m unittest discover -s omi/firmware/research/owner_ota/host -p test_workflow.py
```

## Before a controlled physical trial

Engineering still needs real fixed-area storage/lease and SPU/peripheral/DMA
ownership readback, normal Secure/Nonsecure interrupt/scheduler integration, trusted health and
owner-session/enrollment confirmation, independent recovery/repair entry,
qualified RF/power/reset fixtures, target Oberon execution and worst-case stacks.
The first legacy OTA migration remains an explicit unresolved risk/decision.
This host driver is NOT a protected production supervisor or phone client.

Current target hold must be explicitly released for an exact reviewed target,
artifact hashes, operations/write ranges, data loss and recovery plan. Reuse prior
bench permission where it covers that plan; do not infer new authority from PASS.
Bootloader/trust/key/permanent-protection changes, electrical fixture installation,
purchases/new-machine access or production rollout need their own explicit owner
approval. No permission or physical action is requested by running this demo.
No real backend, key generation, supervisor signing, upload, commit or push here.

## Disabled target adapter slice

The [fixed-bank target storage adapter](target_adapter/README.md) compiles against the pinned Secure Zephyr/Nordic APIs and binds to the shared C source interface. Its target initializer always refuses with ENOTSUP: shared-bus ownership and reset epochs remain unqualified. It is not part of this host simulator or production build. [Owner confirmation](target_adapter/owner-confirmation.md) distinguishes owner authority, health and image signatures.
