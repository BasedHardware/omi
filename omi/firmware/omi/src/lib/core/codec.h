#ifndef CODEC_H
#define CODEC_H
#include <zephyr/kernel.h>

// Callback
typedef void (*codec_callback)(uint8_t *data, size_t len);
void set_codec_callback(codec_callback callback);

// Integration

int codec_receive_pcm(int16_t *data, size_t len);

/**
 * @brief Initialize the Codec
 *
 * Initializes the codec
 *
 * @return 0 if successful, negative errno code if error
 */
int codec_start();

/**
 * Drain all PCM accepted before the microphone stopped through the encoder and
 * output callback.
 *
 * @param timeout_ms Maximum time to wait for the codec/output pipeline
 * @return 0 when drained, -ETIMEDOUT otherwise
 */
int codec_drain(uint32_t timeout_ms);

#endif
