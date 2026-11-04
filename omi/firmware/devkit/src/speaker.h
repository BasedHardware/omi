#ifndef SPEAKER_H
#define SPEAKER_H

#include <zephyr/kernel.h>
/**
 * @brief Initialize the Speaker
 *
 * Initializes the speaker
 *
 * @return 0 if successful, negative errno code if error
 */
int speaker_init();

/**
 * @brief Endpoint function for streaming audio
 *
 * Call this function in the following way (Via ble)
 * 1. Send a 4 byte little-endian packet containing the audio data size in bytes
 *    (16-bit signed mono, 8 kHz). A 4-byte packet arriving mid-stream is
 *    treated as audio; it re-arms as a header only once the stream is idle or
 *    the host has been quiet for ~2 s.
 * 2. Send the PCM as writes of at most 400 bytes. The device notifies after
 *    every write to pump the next one.
 * 3. Every block of the stream is queued while the I2S peripheral is idle and
 *    a single START fires when the bytes written reach the declared size, so
 *    the clip plays without gaps. One stream must therefore fit the device
 *    queue: at most ~7 blocks (~2.2 s of audio). Longer text should be split
 *    into several step 1-3 transmissions at sentence boundaries, where the
 *    inter-stream gap lands as a natural pause.
 * 4. If the host stalls longer than the re-arm window mid-stream, the
 *    unfinished stream is abandoned when the next header re-arms; the re-arm
 *    also recovers the peripheral from any error state, so a stalled or
 *    over-long transmission never poisons later audio.
 *
 * @return The amount of data successfully sent in bytes.
 */
uint16_t speak(uint16_t len, const void *buf);

/**
 * @brief Play a chime effect
 *
 * This function plays a chime effect. Use this to check if the speaker works correctly
 *
 * @return 0 if successful, negative errno code if error
 */
int play_boot_sound();

/**
 * @brief Play the "speak now" cue (two ascending blips)
 *
 * Called on double-tap so the user learns audibly that a voice-agent turn has
 * been opened for the paired app. No-op when no speaker is initialized; skipped
 * while a BLE audio stream owns the queue.
 */
void play_talk_cue(void);

/**
 * @brief Initialize the Haptic Pin
 *
 * On Call, activates the haptic pin
 *
 * @return 0 if successful, negative errno code if error
 */
int init_haptic_pin();

/**
 * @brief Activate the haptic pin for a given duration
 *
 * On Call, starts the haptic pin, creating a vibration for the given duration in milliseconds
 *
 * @return a sound hopefully
 */
void play_haptic_milli(uint32_t duration);

void speaker_off();

void register_speaker_service();

#endif
