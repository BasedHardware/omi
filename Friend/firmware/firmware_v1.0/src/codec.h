#ifndef CODEC_H
#define CODEC_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <zephyr/sys/ring_buffer.h>

// Expose codec ring buffer for voice interaction
extern struct ring_buf codec_ring_buf;

// Voice mode functions
void set_voice_mode(bool enabled);

// Callback
typedef void (*codec_callback)(uint8_t *data, size_t size);
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

#endif