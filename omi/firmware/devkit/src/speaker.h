#ifndef SPEAKER_H
#define SPEAKER_H

#include <zephyr/bluetooth/conn.h>
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
 * 1. Send a 4 byte little-endian packet containing the audio data size
 * 2. Send to the ble notify id 400 byte packets (with notify), with each 2 bytes being the audio data
 * 3. Repeat step 2 until the audio data is sent. Then the speaker will automatically play the sound
 * when the audio data sent is equal to the audio data size sent in step 1
 *
 * @return The amount of data successfully sent in bytes.
 */
int speak(uint16_t len, const void *buf, struct bt_conn *conn);
void speaker_reset_stream(void);
// Transport supplies the version-2 drain notification after DMA releases the block.
void speaker_notify_complete(struct bt_conn *conn, bool success);

/**
 * @brief Play a chime effect
 *
 * This function plays a chime effect. Use this to check if the speaker works correctly
 *
 * @return 0 if successful, negative errno code if error
 */
int play_boot_sound();

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
