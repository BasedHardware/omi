#include "mic.h"

#include <driver/i2s.h>

#include "config.h"

// I2S configuration for PDM microphone
#define I2S_PORT I2S_NUM_0

// Static variables
static volatile bool mic_running = false;
static mic_data_handler audio_callback = nullptr;
static int16_t *i2s_read_buffer = nullptr;

bool mic_start()
{
    if (mic_running) {
        Serial.println("Microphone already running");
        return true;
    }

    Serial.println("Initializing I2S PDM microphone...");
    Serial.printf("  CLK Pin: GPIO%d\n", MIC_CLK_PIN);
    Serial.printf("  DATA Pin: GPIO%d\n", MIC_DATA_PIN);
    Serial.printf("  Sample Rate: %d Hz\n", MIC_SAMPLE_RATE);

    // Allocate buffer in PSRAM for better performance
    if (i2s_read_buffer == nullptr) {
        i2s_read_buffer = (int16_t *) ps_malloc(MIC_BUFFER_SAMPLES * sizeof(int16_t));
        if (i2s_read_buffer == nullptr) {
            Serial.println("Failed to allocate mic buffer in PSRAM!");
            // Try regular malloc as fallback
            i2s_read_buffer = (int16_t *) malloc(MIC_BUFFER_SAMPLES * sizeof(int16_t));
            if (i2s_read_buffer == nullptr) {
                Serial.println("Failed to allocate mic buffer!");
                return false;
            }
            Serial.println("Using regular RAM for mic buffer");
        } else {
            Serial.println("Using PSRAM for mic buffer");
        }
    }

    // I2S configuration for PDM microphone
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t) (I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_PDM),
        .sample_rate = MIC_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 256,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0,
    };

    // I2S pin configuration for XIAO ESP32S3 Sense PDM microphone
    i2s_pin_config_t pin_config = {
        .bck_io_num = I2S_PIN_NO_CHANGE,
        .ws_io_num = MIC_CLK_PIN,   // PDM CLK
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = MIC_DATA_PIN, // PDM DATA
    };

    // Install and configure I2S driver
    esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    if (err != ESP_OK) {
        Serial.printf("Failed to install I2S driver: %s\n", esp_err_to_name(err));
        return false;
    }

    err = i2s_set_pin(I2S_PORT, &pin_config);
    if (err != ESP_OK) {
        Serial.printf("Failed to set I2S pins: %s\n", esp_err_to_name(err));
        i2s_driver_uninstall(I2S_PORT);
        return false;
    }

    // Clear DMA buffers
    i2s_zero_dma_buffer(I2S_PORT);

    mic_running = true;
    Serial.println("Microphone started successfully");
    return true;
}

void mic_stop()
{
    if (!mic_running) {
        return;
    }

    Serial.println("Stopping microphone...");

    i2s_stop(I2S_PORT);
    i2s_driver_uninstall(I2S_PORT);

    mic_running = false;
    Serial.println("Microphone stopped");
}

bool mic_is_running()
{
    return mic_running;
}

void mic_set_callback(mic_data_handler callback)
{
    audio_callback = callback;
}

void mic_process()
{
    if (!mic_running || i2s_read_buffer == nullptr) {
        return;
    }

    size_t bytes_read = 0;
    esp_err_t err =
        i2s_read(I2S_PORT, i2s_read_buffer, MIC_BUFFER_SAMPLES * sizeof(int16_t), &bytes_read, pdMS_TO_TICKS(20));

    if (err == ESP_OK && bytes_read > 0) {
        size_t samples_read = bytes_read / sizeof(int16_t);

        // Apply gain if needed
        if (MIC_GAIN != 1) {
            for (size_t i = 0; i < samples_read; i++) {
                int32_t sample = (int32_t) i2s_read_buffer[i] * MIC_GAIN;
                // Clamp to 16-bit range
                if (sample > 32767)
                    sample = 32767;
                if (sample < -32768)
                    sample = -32768;
                i2s_read_buffer[i] = (int16_t) sample;
            }
        }

        if (audio_callback != nullptr) {
            audio_callback(i2s_read_buffer, samples_read);
        }
    }
}
