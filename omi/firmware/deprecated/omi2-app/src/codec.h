/**
 * @file codec.h
 * @brief Audio codec interface for audio compression
 * 
 * This module provides encoding and decoding capabilities for audio data,
 * using the Opus codec for efficient audio compression. It manages the
 * conversion between raw PCM audio samples and compressed audio data for
 * transmission over Bluetooth or storage on the SD card.
 */
#ifndef CODEC_H
#define CODEC_H
#include <zephyr/kernel.h>

/**
 * @brief Callback function type for encoded audio data
 * 
 * Function pointer type for callback that receives encoded audio data
 * after compression. This callback is typically used to transmit the
 * compressed audio data over Bluetooth or write it to storage.
 *
 * @param data Pointer to encoded audio data
 * @param len Length of encoded data in bytes
 */
// Callback
typedef void (*codec_callback)(uint8_t *data, size_t len);

/**
 * @brief Set the callback function for encoded audio data
 * 
 * Registers a callback function that will be called whenever new
 * encoded audio data is available from the codec.
 *
 * @param callback Function pointer to call with encoded audio data
 */
void set_codec_callback(codec_callback callback);

/**
 * @brief Process raw PCM audio data for encoding
 * 
 * Takes raw PCM audio samples from the microphone and passes them
 * to the encoder. The encoded data will be provided via the registered
 * callback function.
 *
 * @param data Pointer to buffer containing PCM audio samples
 * @param len Number of samples in the buffer
 * @return 0 if successful, negative error code otherwise
 */
// Integration
int codec_receive_pcm(int16_t *data, size_t len);

/**
 * @brief Initialize the Codec
 *
 * Initializes the codec
 * Sets up the Opus encoder and decoder with the appropriate settings
 * for the device's audio requirements (sample rate, bitrate, etc.)
 *
 * @return 0 if successful, negative errno code if error
 */
int codec_start();

#endif