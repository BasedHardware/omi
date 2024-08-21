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
 * @brief Play a tone
 *
 * @param frequency Frequency of the tone in Hz
 * @param duration Duration of the tone in milliseconds
 * @return 0 if successful, negative errno code on failure
 */
int play_tone(uint32_t frequency, uint32_t duration_ms);

/**
 * @brief Play audio from a buffer
 *
 * @param len Length of the audio data
 * @param buf Buffer containing the audio data
 * @return 0 if successful, negative errno code on failure
 */
uint16_t play_audio(uint16_t len, const void *buf);

#endif /* SPEAKER_H */
