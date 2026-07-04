# Hardware AAD (T5838 Acoustic Activity Detection) — Analysis & Bring-up

Summary of the on-device investigation and measurements for driving the TDK
**T5838** microphone's hardware Acoustic Activity Detection (AAD) on the Omi
nRF5340 board. All results were obtained over SWD + SEGGER RTT (no oscilloscope).

## What AAD does

During silence the mic is clocked into **AAD sleep** (PDM clock OFF, ~20 µA). Its
internal analog detector keeps monitoring sound and pulls the **WAKE** pin HIGH
when the level exceeds a programmed threshold, so the MCU can leave the PDM
peripheral off until there is something to record.

## Hardware map (Omi nRF5340)

| Signal | Pin | Direction | Notes |
|--------|-----|-----------|-------|
| PDM CLK | P1.01 | MCU → mic | shared: PDM peripheral **and** GPIO bit-bang for config |
| PDM DATA | P1.00 | mic → MCU | audio |
| THSEL | P1.05 | MCU → mic | one-wire ("FAKE2C") config line |
| WAKE | P1.02 | mic → MCU | AAD interrupt, **active-HIGH** |
| PDM_EN | P1.04 | MCU → LDO | enables 1.8 V rail (mic VDD **and** level-shifter VCCA) |

All of CLK/DATA/THSEL/WAKE cross a **TXS0104 level shifter** (3.3 V ↔ 1.8 V).

## Key findings

| # | Finding | Detail |
|---|---------|--------|
| 1 | WAKE polarity | **Active-HIGH**: HIGH while sound > threshold, returns LOW otherwise (datasheet §pin-4). |
| 2 | Config protocol | AAD registers written via "FAKE2C" bit-bang on **THSEL + PDM CLK** at ~100 kHz; register sequence matches datasheet exactly (unlock `5C/3E/6F/3B/4C`, then `35`=LPF, `36`=TH, `29`=`0x08` enable). |
| 3 | **Root-cause fix** | `dmic STOP` alone does **not** release the PDM CLK pin for bit-banging (even though `nrf_pdm_enable_check()` reads 0). Must call **`nrf_pdm_disable()` explicitly** before the FAKE2C bit-bang, or the config never lands and WAKE stays stuck HIGH. |
| 4 | Power rail constraint | PDM_EN must stay **HIGH during AAD sleep** — it powers both the mic and the level-shifter VCCA; dropping it kills AAD and the WAKE path. |
| 5 | Level shifter | **Not a problem.** TXS0104 passes the ~100 kHz FAKE2C waveform and the WAKE signal fine. |
| 6 | Entry transient | On mic/PDM restart the first **~7 ms (114 samples @16 kHz)** of audio rail to ±32767 (mic settling, matches datasheet ~6 ms wake-up). Unusable. |
| 7 | Edge vs level | If sound is present during AAD entry, WAKE is already HIGH at arm time → an edge IRQ is missed. Handled by re-checking the level right after arming. |

## Measured latency / "swallow"

Measured with a **linear chirp** stimulus (frequency encodes elapsed time since
onset → no clock sync needed). 8 clean captures, chirp slope verified 2832–2940
Hz/s vs 3000 Hz/s generated.

| Component | Value |
|-----------|-------|
| WAKE ISR → mic resume (firmware) | 0–30 µs |
| Acoustic onset → first captured sample (T5838 detect + wake + PDM start) | ≈ 0 ms (< 2 ms, below resolution) |
| PDM/mic restart transient (railed, unusable) | 7.1 ms (very consistent) |
| **Effective swallow (onset → first clean audio)** | **≈ 6 ms** (5.1–6.3 ms, σ 0.44 ms) |

**Implication:** ~6 ms lost at the very start of a sound — far below one phoneme
(~50–150 ms). A word like "hello" is captured intact. The 300 ms VAD debounce that
existed in the old software path is gone in the hardware design (not needed).

## Reliability (stress test)

10 wake cycles (chirp every 8 s, device re-sleeps between):

| Metric | Result |
|--------|--------|
| Chirp → wake | **10 / 10** |
| Clean re-entry to AAD sleep (WAKE idles LOW) | **10 / 10** |
| Stuck-HIGH / freeze | **0** |
| Swallow spread | 5.1–6.3 ms (σ 0.44 ms) |

Extra wakes can occur from ambient noise > threshold — this is intended AAD
behaviour, not a fault. To reduce false wakes in noisy rooms: raise the AAD
threshold, or switch to AAD-D2 (digital) which supports a minimum-pulse-duration
filter.

## Entry / exit sequence (firmware)

**Enter AAD sleep** (after a silence hold, offline only):
1. Mask WAKE IRQ.
2. `mic_pause()` (dmic STOP), settle ~20 ms.
3. `nrf_pdm_disable()` — release the CLK pin.
4. Bit-bang: unlock → LPF/threshold → enable AAD-A → clock >2 ms → park CLK low.
5. Settle (~0.8–1 s), arm WAKE IRQ (rising edge); if WAKE already HIGH, wake now.

**Exit** (on WAKE):
1. Mask WAKE IRQ, hand CLK back to the PDM peripheral.
2. `mic_resume()` (dmic START re-applies pinctrl, reclaims CLK).

## Code layout

- **`src/mic.c`** — owns the mic + hardware AAD: the WAKE ISR, the AAD handler
  thread, enter/exit sleep, PDM-disable, and the silence tracker that runs inline
  in the mic audio path. `mic_start()` powers the rail and starts the AAD handler.
- **`src/t5838_aad.c` / `.h`** — low-level T5838 FAKE2C bit-bang driver
  (register writes, AAD-A config, sleep entry) on raw GPIOs.
- There is no separate `aad.c`; hardware AAD is fully integrated into `mic.c`.
- `main.c`'s mic callback just forwards audio to the codec.

## Config

| Kconfig | Meaning | Default |
|---------|---------|---------|
| `CONFIG_OMI_ENABLE_T5838_AAD` | enable hardware AAD | y |
| `CONFIG_OMI_VAD_ABS_THRESHOLD` | silence threshold for re-sleep decision | 250 |
| `CONFIG_OMI_VAD_HOLD_MS` | silence hold before entering AAD sleep | 10000 |
| `CONFIG_OMI_AAD_SETTLE_MS` | settle time after entering AAD before arming WAKE | 800 |

T5838 AAD-A threshold/LPF are set in `t5838_aad.c` (default 2.0 kHz LPF, 75 dB).
