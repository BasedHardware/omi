/*
 * AAD + VAD gate for Omi
 *
 * Monitors WAKE pin (P1.2) via GPIO ISR, runs VAD state machine,
 * and manages SD card suspend/resume in a background thread.
 */

#ifndef AAD_H
#define AAD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/**
 * @brief Start AAD handler: configure WAKE pin ISR and spawn thread.
 *
 * Call once after mic_start().
 *
 * @return 0 on success, negative errno on failure
 */
int aad_start(void);

/**
 * @brief Process a mic buffer through the VAD gate.
 *
 * Called from the mic callback.  Handles debounce, pre-roll
 * buffering, and SD suspend/resume.
 *
 * @param buffer       Raw PCM samples from the microphone
 * @param sample_count Number of samples in @p buffer
 * @return true  if the frame contains voice — caller should forward to codec
 * @return false if in VAD sleep — frame stored in pre-roll, skip codec
 */
bool aad_process_audio(int16_t *buffer, size_t sample_count);

/**
 * @brief Check if VAD is in sleep mode (low-power).
 *
 * @return true  if VAD is sleeping (mic paused, T5838 hw AAD active)
 * @return false if VAD is active / recording
 */
bool aad_is_sleeping(void);

#endif /* AAD_H */