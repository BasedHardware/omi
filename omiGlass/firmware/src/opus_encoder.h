#ifndef OPUS_ENCODER_H
#define OPUS_ENCODER_H

#include <Arduino.h>
#include <stdint.h>

// Callback type for encoded audio data
typedef void (*opus_encoded_handler)(uint8_t *data, size_t len);

/**
 * @brief Initialize the Opus encoder
 * @return true if successful
 */
bool opus_encoder_init();

/**
 * @brief Encode PCM audio samples to Opus
 * @param pcm_data Input PCM samples (16-bit signed)
 * @param samples Number of samples
 * @return Number of encoded bytes, or -1 on error
 */
int opus_encode_frame(int16_t *pcm_data, size_t samples);

/**
 * @brief Set callback for encoded data
 * @param callback Function to call when encoded data is ready
 */
void opus_set_callback(opus_encoded_handler callback);

/**
 * @brief Process queued PCM data (call from main loop)
 */
void opus_process();

/**
 * @brief Feed PCM data to encoder
 * @param data PCM samples
 * @param samples Number of samples
 * @return 0 on success
 */
int opus_receive_pcm(int16_t *data, size_t samples);

/**
 * @brief Get the codec ID
 * @return Codec ID (20 = Opus)
 */
uint8_t opus_get_codec_id();

#endif // OPUS_ENCODER_H
