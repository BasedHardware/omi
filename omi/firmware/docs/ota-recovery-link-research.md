# CV1 key-free recovery link research

Status: isolated static research, independently reviewed; not deployable firmware.
Legacy OTA bootstrap and maximum-version policy remain held. No target, key,
signing, provisioning, bootloader or protection change occurred.

Omi input baseline e86cda5abb0ea7ff942ac1bcd07261140953812c; existing NCS2.9.0
and toolchain b8efef2ad5. Its source and evidence run was retained outside this repository.
Source is intentionally separate from production build configuration; it is not
yet a portable contributor target. Generated outputs are outside Git.

Real Secure Zephyr BLE/HCI IPC, SMP/CBOR transport, PSA public P256 verification,
owner header/payload/key-fingerprint verification, boot-selection and CMSE
gateway/handoff code link. A separate minimal NS Zephyr kernel links to the
actual Secure import library. No dummy flash or BLE stubs are used. The status
handler is read-only; no updater/upload path is exposed.

| Static result | Secure recovery subset | Minimal NS ABI client |
|---|---:|---:|
| Flash span |245252B|14462B|
| RAM extent |44436B|4240B|
| Flash interval |0x10200–0x4C004|0x54200–0x57A7E|
| RAM interval |0x20002000–0x2000CD94|0x20012000–0x20013090|

The estimated outer container is246100B including existing header/TLV allowance,
below252KiB cap. Only109080 loaded bytes remain after excluding136160B padding
before the fixed gateway at0x4BFE0; padding still counts for transfer/container
extent. Static RAM is not runtime peak or a two-kernel coexistence proof.

Secure ELF SHA256:
`7bf7584b3634cfc563171cda3e3728fb358e0b024dcf4982a197fbe3c1ab82d4`

NS ELF SHA256:
`90bf52d1575782ea5a702a20151bea69c7ebc22cab4c78e711c6c6985418f142`

Nine isolated host methods pass: actual portable C parsing/selection/vector
bounds, public NIST primitive verification, proposed protection generation and
research-descriptor rejection. Target PSA code was linked, not executed. No
valid full owner-container signature was produced or tested. This count is
separate from the existing184-method contributor suite and shared-C iterations.

Missing engineering: immutable Secure input snapshots and authenticated-vector
binding, protected SD/NOR proxy, durable journals/copy, owner enrollment/session,
button/watchdog recovery, actual SPU init/readback, normal monitor versus recovery
startup, and phone OTA. Secure Zephyr HCI currently attempts NW Secure attribution
where the contract requires locked NW-origin NS; link success does not reconcile
that hook. Do not assume two Zephyr kernels can simply run together after a jump.

Generated policy now permits only S RW/NX journals/persistence; personal flash is
S RW/NX during reset-exclusive copying and NS RX/noW after a separate normal
reset. It is not applied to hardware. Review found and corrected read-only S
journals and an empty-stack lower-bound check. The SDK verify-only Oberon build
warning remains recorded; signing/key-generation functions are absent from final
symbols. These are limited static results, not recovery/security qualification.

Next: implement a small immutable image frontend and durable broker with host
fault injection, then measure the added real code. Keep migration decision and
physical RF/power qualification independent. No consumer workflow or owner-key
enrollment is claimed available today.


## Subsequent immutable-image and journal/copy slice

Isolated production-intended C modules now replace the earlier private owner
parser/verification helpers in the research link. Exact shared implementation:
`secure_image.c`, `secure_store.c`, `secure_services.h`. The run evidence was retained outside this repository.
These are internal Secure functions, not NS gateways or a deployed updater.

Admission snapshots the complete bounded container, checks board/ABI/network
policy, canonical layout and signed/hash-covered vector/entry bounds. Copy
rehashes the snapshot, records intent, erases only fixed personal pages, and
checks exact readback. Two4KiB journal pages use dual-rail256B records, sequence,
CRC and commit-last writes. Preparation creates a smallSecure descriptor and
wipes the large snapshot before final attribution. Authorization requires real
isolation readback and commits TRIAL to both pages before token issuance.
One corrupted committedTRIAL record cannot resurrect olderVERIFIED. No owner
confirmation/session or corrupt-journal repair protocol is exposed.

15 host methods pass underUBSan, including46720 simulated cut-prefix cases and
6144 single-record bit faults. SHA256 is real; service signature acceptance is
an explicit oracle, not a positive signed owner-container proof. These are host
flash semantics, not physical durability, analog fault or SPU evidence.

Current unsigned services ELF:
`64009e14302a340c56dd7d7806c598b47bd19f68dc07e1ea8a9937bc774a5b7f`

Flash span remains245252B/estimatedcontainer246100B; loadedbytes excluding NSC
padding110364B. StaticRAM437732B leaves12828B of440KiB; fullsnapshot393280B is the
major cost. NormalSecure stack/descriptor/backend placement is NOT established:
recoverymain/ISRstacks are above normal64KiB Secure window. HCI attribution and
the missing real readback/flash backend remain explicit blockers. A torninitial
journal or both-invalid metadata remains recovery-only pending separately
reviewed repair; invalid metadata is never silently erased. No deployment,
legacy migration, max-version, protection, signing or target authority follows.

Independent local source review accepted the fixes within trusted-callback and
exclusiveSecure ownership assumptions. Next engineering work is normal monitor
placement/startup, immutable-storage lease versus snapshot memory budget, real
bounded backend and explicit protected recovery repair. Production configuration
and existing monorepo code were preserved; isolated source is not a portable
contributor target yet.


## Streaming-memory reconciliation supersedes the snapshot allocation

The earlier44436→437732B jump was393296B:393280B fullsnapshot plus16B othergrowth.
That temporary snapshot is removed in a new isolated run, retained outside this repository.
BSS400879→8223B saves392656B; noinit34868→43060B adds8192B for larger stacks.
Current metadata is624B, not384KiB. Final Secure staticRAM53268B fits an enforced
65536B PM/linker cap; main/SMP/ISR/allallocatedsections are below0x20012000.

CPUAPP512KiB is partitioned8KiBPCD+64KiBSecure+376KiBpersonalNS+64KiBHCI.
CPUNET's separate64KiB is not extra appRAM. The personal allocation385024B is
preserved, not reduced to the Secure headroom12268B. Retained flat Omi336088B
leaves48936B arithmetic allowance; no real NS app port/runtime peak has been
measured. Capacity is plausible, overall execution is not yet qualified.

Streaming C holds cached signed metadata and an exclusive Secure-storage lease,
uses512B chunks, checks vector bytes in the same signedpayloadhash pass, rechecks
payloadhash in the container pass, and hashes actual destination beforeVERIFIED.
Cached generation/payloadlength are bound to authenticated prefix. Actual storage
ownership backend is still absent; a nonce/checkcallback is not protection proof.
The journal/copyslice remains shared C, not a second policy model.

Configured main/management stacks8KiB each and heap8KiB are included in53268B.
AppGCC stream_hash frame1600B; a known-own-code nestedpath2080B beforeSDK callees.
OpaqueSDK/backend depths prevent a total runtime worstcase claim. RealtargetPSA
hashoperation432B is bounded by fixed512B state storage. No perimageheap/buffer.

The isolated HCI source graph now excludes the original Secure-attribution-write
hook and uses a read-only guard requiring lockedNWNonsecure/userselectable state.
It refuses mismatches without writes. This resolves sourceclobber behavior and
staticstackplacement; actualSPU setup/storagebackend/dualRTOS execution remain
unqualified. ProductionSDK/configfiles unchanged.

17 hostmethods pass underUBSan (existing46720simulatedcuts/6144bitfaults retained).
Separate native softwarePSA now accepts publicNIST verification and rejects hash/
signature/wrong-container changes with realPSA; no keys generated. Fullpositive
signedownercontainer and targetOberon runtime remain unproved. Servicefaulttests
still label their signatureoracle explicitly. Researchartifact admission rejects.

Final unsignedELF:
`1c738f5cd86d5476b2f9cb0197a75f58406f7105863a093640c506428da17ba0`.
Static source/linkage review passed; no deployment, target, trust, signing or
legacy migration action follows. This supersedes only the snapshotRAM and static
stackplacement limitation, not the other missing runtime/backend/recovery gates.


## Actual PSA full-container and first NS module integration

The next isolated run was also retained outside this repository.
The admission boundary now uses the actual C PSA adapter/native softwareMbedTLS,
not a signatureoracle.39 fullcontainer cases (3accepted/36rejected),9UBSanhost
methods pass; aggregate returncode/output and fixture/source hashes are retained
in RUN-actual-psa.json. Positive includes the actual compiled NSmodule payload,
maximumcontainer and standardECDSA highS variant. Signedcompatibility negatives,
key-ID/signer mismatch, domainNUL/doublehash, truncation, vector/MSP, padding and
finaldestination mutation/source-race cases reject as intended.

Host fixtures alone use pre-existing PUBLIC NONSECRET NIST CAVS11.2 P256 test
keys from pinnedSDK tests. Scalars are not persisted into this run or present in
runtime ELF; no production/owner credential or enrolled key is used. Testfixture
signing was explicitly authorized; outer researchELFs remain unsigned. Runtime
owner_policy_present=false andgraphs exclude fixtures/host models. Existing
artifact admission rejects bothELF descriptors and fixtureJSON. No production
signing/trust/protection change.

Exactsignature input: SHA256 once over17B NUL-terminatedCV1-OWNER-APP-v2 plus128B
canonicalheader (145B). ECDSA PrehashedSHA256 producer/PSAverify_hash consumer,
rawr32||s32 bigendian; noDER/doublehash. Payload/key fingerprints are headerfields.
BothvalidS forms are accepted perstandardPSA; no unique-signature/lowSreleasepolicy
claim. Independentpublic reviewverified20signedfixtures andexact NS ELFpayload.

The active monorepo audio_packet_logic.c/h is compiled unchanged into a real
NS Zephyr slice checking theexistingSecureABI gateway before synthetic packing.
Bothreal functions+gateway are linked; no microphone/BLE/storage hardware.
NS14862Bflash/4384BRAM; Secure53268B remainsinside64KiB, app376KiB preserved.
It is a moduleport/link slice, not fullNSapp or Secureaudiotransport/runtimeproof.

CurrentunsignedELFs:
S03266808c59cfe7938d013059410ad0016cf4277caaa79370d00915983f97b4b
NS6e5640d02d508b6a3c2dc1adb21ec0891e36337039aae7e4418a52526eb8e760.

Independentreviewfound no substantive format/prehash/keyisolation/module defect
and reconciledfinalreceipts. NativePSA cryptographic admission is established for
thesehostfixtures; targetOberon, physicalstorage/SPU/HCI, dualkernel execution,
stackpeaks, enrollment/recovery and legacy migration remainunqualified/held.
