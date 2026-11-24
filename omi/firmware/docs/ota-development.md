# Everyday personal firmware OTA on CV1: feasibility decision

**Required outcome:** an everyday owner can build/install personal firmware from a phone without a jig or maintainer approval per build, and recover from a failed personal app without opening the device. Independent review disposition: Option A is a plausible future architecture but is **not cleared for implementation or an interruption-safe bootstrap claim**. Retain it as a conditional candidate; resolve migration and runtime boundary gates before deployment. Isolated key-free static research may proceed independently of legacy migration. This is a source-backed design and arithmetic/state simulation, not implemented firmware, a migration approval or a promise about every shipped device.

Current runnable capability is [host checks and key-free app-object compilation](../tools/cv1/README.md). Neither current firmware nor those tools implements owner enrollment, a protected recovery supervisor or automatic personal-app revert. No bootloader, key, protection, partition, device or phone behavior was changed for this design.

## Independent source review: implementation hold

The in-place review found a reachable conventional-version bootstrap failure in the retained loader. After primary erase, a cut after the first20 header bytes can leave valid magic/sizes/flags but an erased version255.255.65535. `swap_scratch.c:976–993` raw-reads it; `loader.c:2367` selects a pending update before primary authentication. Secondary validation compares this primary version first (`1169–1229`) and can erase the valid secondary as a downgrade, then fail to boot the partial primary. `boot_check_header_erased:1057–1083` tests only whether magic is allFF. Copy starts at offset0 in1024B chunks, and linked `soc_flash_nrf.c:480–512` writes ascending4B words. This is independently verified source-level reachability, not a reproduced hardware brick.

The bounded [bootstrap/ownership contract](ota-bootstrap-contract.md) characterizes the exact source path and remaining limits. Maximum comparison version255.255.65535 has no downgrade-erasure failure in its admitted cut classes, with build ignored. It has **not** been adopted: equal maximum versions are accepted, so root semantic antirollback is lost, and a validly signed but broken first supervisor still has no functional fallback. Merely raising the supervisor version above zero is insufficient. A safer loader in future manufacture is a different cohort; replacing this FPROTECT-locked loader OTA is not an established fallback.

Other concrete review gates:

* Default pinned TF-M attributions expose SPIM3, reset/regulators, NVMC, watchdogs and all GPIO pins unless overridden. They do not implement the proposed boundary. `tfm_peripherals_config_nrf5340_application.h:14–28,94–96,142–148,238–260`; `common/core/target_cfg.c:1490–1515`.
* TF-M locks the network external domain Non-Secure (`target_cfg.c:1617–1626`), while Secure/non-NS Zephyr recovery HCI setup attempts to set it Secure (`zephyr/drivers/bluetooth/hci/nrf53_support.c:29–44`). Reset-mode attribution and initialization order must be explicit, including readback/fail-closed behavior. Fixed radio bytes do not prove fixed privilege or behavior.
* MCUboot's `pcd_lock_ram(true)` fixes the first8KiB PCD reservation Non-Secure/read-only until reset (`nrf/subsys/pcd/src/pcd.c:267–272`); do not repurpose it for the monitor.
* Existing SD code changes CS and suspends shared SPIM3. A bounded trusted SD/storage proxy and complete pin/DMA/alias policy are required, not a config-only NS rebuild. Current long-press recovery is app work that can tear down BLE/storage, disable watchdog and enter system-off.
* The proposal now uses erase-aligned384/384/64KiB banks, with a256/256/256/64KiB alternative in the contract. The retained NOR driver requires4KiB alignment and erases no more than the requested range; it does not round400KiB up. A future caller that rounds to advertised64KiB layout boundaries could cross48KiB into the old sketch’s next bank. This is a conditional caller risk, not retained driver behavior. Neither layout is implemented or authorized for flash.
* Isolated key-free research now links real Secure BLE/SMP/PSA recovery components and a separate minimal NS Zephyr gateway client; that static link research is recorded in a separate change. Protected proxies, runtime attribution and normalS/NS execution are still absent; the measured subset does not prove the complete recovery system fits or works.

Deployment remains held. Subsequent authorization permitted strictly offline/key-free link research without resolving legacy migration; its limited static result passed in-place review. Remaining work includes immutable authenticated-input binding, durable Secure storage/copy, normal monitor/recovery startup composition and runtime attribution. No target, key or bootloader changes followed from this research.

## What the retained baseline permits

Baseline `e86cda5abb0ea7ff942ac1bcd07261140953812c`, NCS2.9.0. Generated partition map hash is `345f6b77aa32407ed2aaf33c8d2d7809b37e37a68f920ad30fd5fb647a4d1f5a`. Exact maps/public evidence are in `../tools/cv1/pinned-partitions.yml`, `../tools/cv1/preflight-evidence/validation-evidence.json` and `../tools/cv1/ota-development-plan.json`.

| Existing resource | Range / capacity | Consequence |
|---|---|---|
| MCUboot | `0–0x10000`,64KiB | FPROTECT locks this range before app handoff; no configured bootloader OTA image. |
| App header / usable app | `0x10000–0x10200` / `0x10200–0xF6000` | Current whole signed app is248,516bytes. The primary *container* nevertheless spans to`0x100000`; it overlaps persistence in the generated map. |
| Littlefs / settings | `0xF6000–0xFC000` / `0xFC000–0xFE000`,24/8KiB | Keep these addresses in the proposals; do not infer rollback-safe data semantics. |
| Internal tail | `0xFE000–0x100000`,8KiB | Legacy MCUboot trailer uses the end of the primary slot; do not place owner records there. |
| NOR app/network staging | `0–0xF0000` / `0xF0000–0x130000`,960/256KiB | These offsets are compiled into existing MCUboot. Do not overlay them with personal images. |
| NOR unused | `0x130000–0x200000`,832KiB | Proposed two384KiB personal banks plus64KiB metadata; alternative three256KiB banks plus64KiB. |
| Network core |256KiB flash,64KiB RAM | Existing b0n/provision envelope`0x01000000–0x01008800`; radio follows. First-stage personal development keeps all of it unchanged. |

Current MCUboot is RSA-PSS2048/SHA256, overwrite-only FAST, software downgrade prevention enabled, hardware downgrade counter disabled, serial recovery disabled. Image roles are0(app),1(network); MCUboot itself is`-1`/not updateable. Network b0n is hash-only, not provision-key ECDSA authentication; app-core outer validation is separate. See [validation model](validation-model.md).

Pinned `bootutil/src/image_validate.c:124–130` hashes the declared header/image/protected-TLV extent, not the entire primary partition. `loader.c:boot_copy_image` erases/copies sectors covering the new image plus the primary trailer in FAST mode; it does not provide old-app revert. `boot/zephyr/main.c:625–645` protects MCUboot, not all future app code. These facts support investigating a small official signed supervisor at the current app address with personal code outside its signed extent. They do not prove an OTA bootstrap or interruption recovery works.

## Privilege and independent recovery

The current app is not a demonstrated Secure/Non-Secure split: both generated `TRUSTED_EXECUTION_SECURE` and `TRUSTED_EXECUTION_NONSECURE` are off. An arbitrary replacement at that privilege level cannot be relied upon to preserve recovery. The repository's `_ns` board is only scaffolding with different default flash/RAM partitions; changing the board name alone is insufficient.

Nordic documents16KiB flash/8KiB RAM SPU regions with lockable permissions, and secure attribution for peripherals/pins and cross-domain access. NVMC can be secure-only; UICR writes from non-secure code fault. These support a supervisor/NS boundary, not a proof of our eventual implementation. [SPU specification](https://docs.nordicsemi.com/r/bundle/ps_nrf5340/page/spu.html), [NVMC specification](https://docs.nordicsemi.com/r/bundle/ps_nrf5340/page/nvmc.html).

Required enforcement in either option: trusted code owns SPU setup, NVMC/UICR/reset/power controls, secure watchdog and recovery-button handling. Personal firmware runs Non-Secure and cannot rewrite the supervisor, owner/trial journals, recovery selection or permanent configuration. SPI3 is shared by NOR and SD in the retained DTS; protect its pins/peripheral and provide a bounded storage proxy. Merely marking internal flash secure does not protect external backup banks from raw SPI commands or GPIO bit-banging. CPUAPP cannot directly access CPUNET peripherals/NVMC or flash; PCD is the privileged indirect path. PCD mailbox and external-domain accesses still need explicit negative tests; an unblocked path invalidates the recovery claim. Do not assume an app-only package-role rule alone enforces this boundary.

Concrete board-source ownership includes buttonP0.26 and power controlP0.5; SPI3 SCK/MOSI/MISO P1.7/P1.9/P1.8; SD/NOR chip selects P1.11/P0.11; NOR WP/HOLD P0.19/P0.10. These are retained DTS/pinctrl facts for attribution design, not jig wiring instructions or proof of every physical revision. The shared bus means an unchanged NS SD driver cannot simply keep raw peripheral ownership while NOR backup is called protected.

The existing user button is GPIO0.26 and currently polled by app work; it is not proven to be a hardware reset. A button-at-boot-only loader would therefore be insufficient. The proposed supervisor must own a secure button interrupt/timer while personal code runs, able to select recovery/reset independently of NS interrupt masking, BLE, self-confirmation or app power-off requests. No new physical gesture is declared working today. Secure resources must be re-established before every NS handoff, with external-domain access restricted. No permanent debug/provision lock is proposed.

## Two concrete options

### A — keep current MCUboot, install a resident secure supervisor through trusted app OTA

One official image at the existing app address contains a secure runtime monitor and minimal BLE/SMP recovery host. Its signed extent stops before owner/personal regions. It validates owner-signed inner NS images and manages bounded copy/trial/revert itself; this is **not** enabling MCUboot revert. Personal updates never rewrite the supervisor or legacy MCUboot staging/trailer. Its protected recovery endpoint survives a broken or self-confirmed NS app.

The artifact topology is a hard gate: pinned `nrf/cmake/sysbuild/image_signing.cmake:157–161` uses `tfm_merged` when `BUILD_WITH_TFM` is enabled. A default combined S+NS signed image would make every personal NS update invalidate the outer MCUboot signature. Option A therefore needs an explicitly supervisor-only signed outer extent and separately authenticated inner NS artifact. All Secure executable sections/veneers must be inside that signed prefix; mutable owner code must be outside it. No existing TFM/sysbuild switch is claimed to provide this arrangement automatically.

| Proposed internal region | Range | KiB |
|---|---|---:|
| Existing MCUboot |`0–0x10000`|64|
| Supervisor + guard |`0x10000–0x50000`|256|
| Owner journal |`0x50000–0x54000`|16|
| NS personal slot |`0x54000–0xF0000`|624|
| Trial journal |`0xF0000–0xF4000`|16|
| Gap / existing littlefs / settings / tail |`0xF4000–0x100000`|8+24+8+8|

Supervisor whole signed image cap is252KiB, leaving a4KiB guard within its256KiB envelope. This matters: the retained FAST copy code rounds its write length and can add a write unit even for an aligned image. It must not reach owner records. The observed full signed stock image is242.69KiB, but it is not a usable supervisor: the new recovery/proxy/NS split still needs a link proof below252KiB. Do not treat that old image's size as proof.

| Proposed NOR region | Range | KiB |
|---|---|---:|
| Existing official app staging, untouched by personal updates |`0–0xF0000`|960|
| Existing network staging, unused in personal stage1 |`0xF0000–0x130000`|256|
| Personal candidate |`0x130000–0x190000`|384|
| Last known good |`0x190000–0x1F0000`|384|
| Personal metadata |`0x1F0000–0x200000`|64|

Thus stage1 admits at most384KiB **whole personal containers**, despite624KiB internal space; a512B header plus4KiB tail allowance leaves379.5KiB planned payload budget. Actual format overhead must remain inside that cap. No extra flash purchase is assumed. The baseline signed app fits the cap, but an NS rebuild with proxies/ABI must be measured.

Normal RAM proposal: keep8KiB PCD reservation at`0x20000000`, reserve64KiB secure at`0x20002000–0x20012000`, allow376KiB NS to`0x20070000`, keep64KiB radio IPC to`0x20080000`. Historical size-tool data+bss totals336,754bytes; exact allocated RAM section address extent is336,088bytes (`0x20002000–0x200540D8`, including214,192B noinit), leaving48,936 arithmetic bytes against376KiB NS. These are distinct metrics, not stack/heap high-water proof or a Secure recovery fit. Preferred execution contract for the next design revision: normal operation retains only a small Secure monitor/IRQ/watchdog path; a protected gesture resets into an exclusive recovery boot with NS stopped. Recovery may then reclaim/wipe the normal NS arena before locking attribution, preserving PCD and IPC reservations. Do not assume two full Zephyr kernels run concurrently or change already locked regions in place. The actual monitor/recovery composition and stack/data initialization still need specification and link proof. Existing `_ns` defaults allocate only192KiB NS and do not fit the observed app.

No third golden stock bank fits alongside two384KiB banks in the unused NOR. The phone app must bundle/cache a compatible maintainer-signed **NS stock** image. A protected gesture starts the supervisor's own BLE recovery; the phone transfers that stock image without the old owner key. It is not reinstalling the legacy flat Secure3.0.21 binary into an NS slot. If the backup bank is corrupt, recovery remains available and a verified stock transfer can restore the NS slot; interrupted recovery transfer stays in recovery. Automatic trial revert still requires a valid protected previous bank. This distinction avoids promising offline autonomous return-to-stock without a phone or healthy storage.

Bootstrap is a normal maintainer-authenticated app-only OTA in principle; native client app-only packaging/handling and postboot identity still require qualification. No bootloader/key change is needed *if* the retained header/copy/protection behavior and new supervisor design hold. The bootstrap itself uses old overwrite-only machinery and lacks automatic runtime revert. Its risk is not magically repaired by the resulting supervisor. Subsequent official supervisor maintenance is also a separate privileged, interrupted-update problem; personal-update safety must not be advertised as covering it.

The supervisor migration/version rule is unresolved after the interruption finding above; a version merely above the baseline's zero is not safe. A future protected maintenance floor must survive owner reset, but cannot repair the old-loader bootstrap by itself. A valid old flat Secure stock image must not be accepted as an owner/return-to-stock image and remove the boundary. Current software downgrade prevention is useful evidence, not a permanent monotonic-counter guarantee. Legacy maintenance staging stays behind the supervisor's distinct privileged protocol; personal NS code receives no raw path to it. This policy and reset/partial-primary cases require negative artifact/runtime tests before claiming continuity.

### B — replace MCUboot with owner delegation and internal app swap/revert

Budget a new96KiB MCUboot,64KiB secure monitor,16KiB owner journal, two384KiB NS slots and16KiB scratch, then the same16KiB trial journal and preserved upper data/tail. Exact ranges are in `ota-development-plan.json`: slots`0x2C000–0x8C000` and`0x8C000–0xEC000`.384KiB whole-image cap leaves379.5KiB planned payload after the same allowance. Keep existing NOR maintenance/network budgets; free832KiB can hold384KiB authenticated stock,32KiB metadata and416KiB spare.

This can use reviewed MCUboot swap/trial mechanics for the NS image, with owner-key delegation and secure monitor gating confirmation. It still needs independent physical recovery, protected SPI/stock data and NS isolation; app self-confirmation cannot be the only authority. New image roles/layout/key hooks and possibly larger boot code need implementation/link tests. A complete new boot chain is not obtained by flipping a generic MCUboot option.

It replaces the currently write-protected bootloader and changes its partition/image-role map. Existing OTA exposes only app/network, so **no supported OTA-only route for this change is currently established**. An app updater cannot simply erase the FPROTECT-locked loader. Future manufacturing can provision a reviewed design; legacy OTA migration needs its own interruption-safe protected mechanism and accepted installed root. Do not silently require consumers to obtain a jig, and do not promise a universal retrofit. Compared with A, B has smaller personal slots and a much harder bootstrap, but a more conventional bootloader-managed trial/copy implementation and on-device stock bank.

## Enrollment, install and recovery contract

1. A maintainer-authenticated bootstrap installs the supervisor for that device's actual board/root/layout/radio ABI. Verify the new protected recovery identity before enabling owner mode. No key generation, signing or bootstrap has been performed.
2. Enrollment requires a deliberate gesture handled by trusted code, an authenticated session and explicit developer-mode consent. Store public owner/developer keys with generation and roles in the protected journal. BLE pairing alone is insufficient; a paired/malicious phone cannot silently enroll, revoke or wipe. Private maintainer keys are never given to owners. Owner builds can be signed locally/by the owner's phone, with no maintainer approval per build.
3. Owner inner manifest binds device family/board, supervisor ABI, stable radio contract, image digest, size, role and enrollment generation. A receives a distinct inner format in its own banks, not the legacy MCUboot slot. Inactive content is verified before activation; protected intent/copy journal commits before NS handoff. A power cut during copy resumes trusted copy/recovery, never boots partial code.
4. Trial has bounded attempts/timeout and supervisor-controlled watchdog. NS self-confirmation is ignored. Acceptance is bound to the exact digest/generation plus protected health/owner acknowledgment; generic phone-native success callbacks are not that proof. Keep the previous bank until commit. Later failures still allow physical protected recovery, even after owner confirmation.
5. Lost phone: physical protected recovery permits destructive owner reset, revoking old generation, and installation of a maintainer-authenticated compatible NS stock image. Clear incompatible user settings with explicit recovery consent; preserve device usability, not an unproven recording/settings rollback promise. No online maintainer approval is required. Enrollment transfer/account anti-theft policy is not assumed implemented.

The protected session must bind the device identity, owner public key, fresh challenge and image/generation; pairing keys/session material belong to trusted storage, not NS firmware. TOFU during deliberate physical enrollment versus an existing manufacturing identity is a protocol choice still to specify, not an attestation capability already present. A deliberately approved compromised owner phone can authorize a malicious personal app; the guarantee is confinement plus independent recovery, not that owner-authorized code is benign. Owner-selected app versions may go backwards for development; enrollment-generation revocation and the supervisor maintenance floor are separate policies.

Initially personal firmware is whole **NS app-only** firmware against the stable network image, not merely plugins and not unrestricted Secure code. The existing `_ns` target needs new attribution/services and memory layout. Later paired-core development needs a protected network loader/update path, radio ABI compatibility, app-domain protections and verified recovery after a bad radio image; b0n hash-only validation and a package-role filter do not establish this. That is staged engineering scope, not rejection of personal paired-core development.

## What can change through the present trusted OTA

| Piece | Current route / limit |
|---|---|
| New app protocol/UI, signed supervisor prefix, secure monitor code | Potential image0 app OTA under already accepted root; source-level feasibility only. Must prove small-copy bounds, NS handoff/isolation and bootstrap interruptions. |
| Personal owner-signed NS builds | No current accepted route. A adds an inner authenticated protocol under the supervisor; B changes bootloader trust. |
| Network controller | Configured image1 path exists, but keep unchanged for stage1. Replacing it risks losing the only radio recovery transport. |
| MCUboot/root verifier, new boot-level owner keys or standard revert mode | Not an updateable image here; FPROTECT blocks direct replacement during app runtime. B requires a separately proven migration. |
| UICR/OTP/protection | No change proposed or authorized. These are not enrollment storage. |

Shipped-device roots, protection and layouts are unknown. Our retained bench bootloader/readbacks do not inventory them; the original locked factory app was erased in the earlier authorized bench trial. A key path existing in the repository does not establish production secret custody or the ability to sign a shipped-device bootstrap. Inventory public trust first; no blind root rotation.

## Acceptance gates once BLE/power fixtures are qualified

| Contract | Required jig/phone evidence, not just simulation |
|---|---|
| Bootstrap without a jig for the consumer | Stock phone installs app-only supervisor over BLE; board/root/layout retained evidence; supervisor recovery advertises and reports identity. Interrupt every erase/copy/trailer phase and demonstrate an OTA-only outcome or explicitly reject unsupported legacy cohort. |
| Owner autonomy/authentication | Owner enrolls through protected gesture, installs two distinct locally built NS images OTA without our signing approval; wrong owner/generation/board/ABI/role/size/signature rejected. A paired phone alone cannot enroll or mutate recovery. |
| Trial and copy durability | Reset/fault before main, hang/disable BLE, self-confirm, disconnect and power cut during each candidate/previous/journal copy stage. No partial candidate executes; prior image or independent recovery remains reachable. |
| Independent return-to-stock | After a confirmed bad app, NS interrupt masking and corrupted user settings, the existing physical gesture still reaches trusted BLE recovery. Lost-phone/new-phone reset plus cached signed NS stock succeeds; no SWD/opening. Validate actual button/wakeup path. |
| Isolation/radio continuity | Audit and non-destructive negative tests for flash/NVMC/UICR/reset/power, SPI/GPIO/DMA, PCD and cross-domain aliases. Secure regions/journals remain intact; network bytes unchanged after personal updates. Reset/reinitialize stable controller before recovery. No permanent protection writes in tests. |
| Resource/migration bounds | Linked supervisor and NS images within declared caps; worst-case stack/heap and flash-write stalls measured; existing-data address preservation distinguished from schema compatibility. Repeated interrupted copy/erase/endurance/error injection. |

Before hardware bootstrap, inspect the actual signed header/TLV/ELF extents: all Secure code covered; owner slot excluded from outer hash; changing only the inner NS image leaves the outer signature valid; altered supervisor bytes reject. Verify small-image erase/copy rounding and legacy trailer behavior with exact generated images, not only address arithmetic. Reject ordinary combined TFM output for option A.

`test_ota_development_model.py` supplies24 deterministic proposed-contract simulations and exact budget checks. Its authorization/signature/physical/isolation inputs and durable copy-state persistence are assumptions; it does not emulate torn flash writes. It neither executes MCUboot nor verifies cryptography, TrustZone, radio, power-loss recovery or bootstrap on hardware. No new controller execution capability is enabled.

Next agent-owned work: implement immutable image admission and durable Secure journal/copy interfaces; resolve normal monitor versus reset-exclusive recovery startup and the HCI attribution hook. Continue measuring real added code without enabling deployment. Legacy bootstrap functional fallback and maximum-version maintenance policy remain separate held gates. Prefer A only if those gates pass; otherwise revise the budget/architecture explicitly. No new user decision is requested now: continue offline implementation research while migration and physical qualification are deferred. The bounded source characterization and concrete proposed ownership contract are recorded separately; neither authorizes migration. Existing owner-only fixture/source/publication items remain batched.

## Source references

Product: `omi/firmware/omi/sysbuild.conf`, `sysbuild/mcuboot.conf`, `boards/omi/{omi_nrf5340_cpuapp,omi_nrf5340_cpuapp_ns}.dts`, `omi-cpuapp_partitioning.dtsi`, `omi/src/lib/core/button.c`, `app/lib/pages/home/firmware_mixin.dart`. Retained generated `.config`, DTS and partition maps, ELF size and OTA header observations are bound in `ota-development-plan.json` and existing public validation evidence. Pinned SDK: `bootloader/mcuboot/boot/bootutil/src/{image_validate,loader}.c`, `boot/zephyr/main.c`, `nrf/lib/fprotect/fprotect_spu.c`, `nrf/modules/mcuboot/hooks/nrf53_hooks.c`, `nrf/cmake/sysbuild/image_signing.cmake`. Hardware context: [Nordic memory map](https://docs.nordicsemi.com/r/bundle/ps_nrf5340/page/chapters/soc_overview/doc/soc_overview.html-memory). These are evidence and proposed allocations, not deployment files.
