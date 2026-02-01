#ifndef MIC_H
#define MIC_H

#include <Arduino.h>
#include <stdint.h>

// Callback type for audio data
typedef void (*mic_data_handler)(int16_t *data, size_t samples);

/**
 * @brief Initialize and start the microphone
 * @return true if successful, false otherwise
 */
bool mic_start();

/**
 * @brief Stop the microphone
 */
void mic_stop();

/**
 * @brief Check if mic is running
 * @return true if running
 */
bool mic_is_running();

/**
 * @brief Set callback for mic data
 * @param callback Function to call when audio data is ready
 */
void mic_set_callback(mic_data_handler callback);

/**
 * @brief Process mic data (call from main loop or task)
 */
void mic_process();

#endif // MIC_H
