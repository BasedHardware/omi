#ifndef SPEAKER_H
#define SPEAKER_H

#include <zephyr/kernel.h>

/**
 * @brief Initialize the speaker (I2S interface)
 *
 * @return 0 if successful, negative errno code on failure
 */
int speaker_init(void);

/**
 * @brief Play a gentle boot sound
 *
 * @return 0 if successful, negative errno code on failure
 */
int play_boot_sound(void);

/**
 * @brief Start an audio playback session
 *
 * @param length Total length of the audio data in bytes
 * @return 0 if successful, negative errno code on failure
 */
int start_audio_playback(uint32_t length);

/**
 * @brief Write a chunk of audio data
 *
 * @param data Pointer to the audio data
 * @param length Length of the audio data in bytes
 * @return Number of bytes written if successful, negative errno code on failure
 */
int write_audio_data(const void *data, uint16_t length);

#endif /* SPEAKER_H */
