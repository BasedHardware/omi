/*
 * Standalone low-level driver for TDK T5838 Acoustic Activity Detection (AAD).
 *
 * This is a minimal, self-contained port of the register-write ("FAKE2C")
 * bit-bang protocol from the Irnas/Brilliant-Labs t5838 driver, stripped of the
 * Alif PDM device coupling so it can be driven directly on nRF5340 GPIOs.
 *
 * Pins (omi board):
 *   THSEL   = pdm_thsel_pin (P1.05)   host -> mic, via TXS0104 level shifter
 *   PDMCLK  = gpio1 pin 1  (P1.01)    shared with nRF PDM peripheral
 *   WAKE    = pdm_wake_pin (P1.02)    mic  -> host
 *   PDM_EN  = pdm_en_pin   (P1.04)    enables 1.8V LDO (mic VDD + shifter VCCA)
 *
 * IMPORTANT: the PDM peripheral MUST be stopped before calling t5838_aad_enter()
 * because the config protocol bit-bangs the PDMCLK line as a GPIO. The 1.8V rail
 * (PDM_EN) MUST stay powered during AAD sleep or the mic and level shifter die.
 */

#ifndef T5838_AAD_H
#define T5838_AAD_H

#include <stdbool.h>

/* Configure GPIOs. Call once at startup. Drives PDM_EN high (mic powered). */
int t5838_aad_init(void);

/* Force the 1.8V mic LDO on/off (PDM_EN). Keep ON for AAD. */
void t5838_aad_power(bool on);

/*
 * Program the T5838 into AAD mode A and clock it into low-power sleep.
 * Precondition: PDM peripheral stopped, mic powered. Bit-bangs THSEL+PDMCLK.
 * Leaves PDMCLK idle low afterwards so the peripheral can reclaim it on resume.
 */
int t5838_aad_enter(void);

/* Release PDMCLK GPIO ownership so the nRF PDM peripheral can drive it again. */
void t5838_aad_release_clk(void);

#endif /* T5838_AAD_H */
