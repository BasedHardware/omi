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
 * 2. Send the PCM as writes of at most 400 bytes (16-bit signed mono, 8 kHz).
 *    The device notifies after every write to pump the next one.
 * 3. Each packet is queued and played as it arrives; playback starts with the
 *    first packet and drains after the byte count written equals the size sent.
 * 4. To stream a second clip while idle, go back to step 1. A length-header
 *    sized packet (4 bytes) arriving mid-stream is treated as audio.
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
