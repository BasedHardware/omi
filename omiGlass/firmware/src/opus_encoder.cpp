#include "opus_encoder.h"

#include <opus.h>
#include <esp_heap_caps.h>

#include "config.h"

// Opus encoder instance
static OpusEncoder *encoder = nullptr;
static opus_encoded_handler encoded_callback = nullptr;

// Ring buffer for PCM data - allocated in PSRAM
static int16_t *pcm_ring_buffer = nullptr;
static volatile size_t ring_write_pos = 0;
static volatile size_t ring_read_pos = 0;

// Output buffer - allocated in PSRAM
static uint8_t *opus_output_buffer = nullptr;
static int16_t *opus_input_buffer = nullptr;

bool opus_encoder_init()
{
    if (encoder != nullptr) {
        Serial.println("Opus encoder already initialized");
        return true;
    }

    Serial.println("Initializing Opus encoder...");

    // Allocate buffers in PSRAM
    pcm_ring_buffer = (int16_t *)heap_caps_malloc(AUDIO_RING_BUFFER_SAMPLES * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (pcm_ring_buffer == nullptr) {
        Serial.println("Failed to allocate PCM ring buffer in PSRAM");
        return false;
    }
    Serial.println("PCM ring buffer allocated in PSRAM");

    opus_output_buffer = (uint8_t *)heap_caps_malloc(OPUS_OUTPUT_MAX_BYTES, MALLOC_CAP_SPIRAM);
    if (opus_output_buffer == nullptr) {
        Serial.println("Failed to allocate opus output buffer in PSRAM");
        heap_caps_free(pcm_ring_buffer);
        pcm_ring_buffer = nullptr;
        return false;
    }

    opus_input_buffer = (int16_t *)heap_caps_malloc(OPUS_FRAME_SAMPLES * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (opus_input_buffer == nullptr) {
        Serial.println("Failed to allocate opus input buffer in PSRAM");
        heap_caps_free(pcm_ring_buffer);
        heap_caps_free(opus_output_buffer);
        pcm_ring_buffer = nullptr;
        opus_output_buffer = nullptr;
        return false;
    }

    int error;
    encoder = opus_encoder_create(MIC_SAMPLE_RATE, 1, OPUS_APPLICATION_VOIP, &error);

    if (error != OPUS_OK || encoder == nullptr) {
        Serial.printf("Failed to create Opus encoder: %d\n", error);
        heap_caps_free(pcm_ring_buffer);
        heap_caps_free(opus_output_buffer);
        heap_caps_free(opus_input_buffer);
        pcm_ring_buffer = nullptr;
        opus_output_buffer = nullptr;
        opus_input_buffer = nullptr;
        return false;
    }

    // Configure encoder for voice
    opus_encoder_ctl(encoder, OPUS_SET_BITRATE(OPUS_BITRATE));
    opus_encoder_ctl(encoder, OPUS_SET_COMPLEXITY(OPUS_COMPLEXITY));
    opus_encoder_ctl(encoder, OPUS_SET_SIGNAL(OPUS_SIGNAL_VOICE));
    opus_encoder_ctl(encoder, OPUS_SET_VBR(OPUS_VBR));
    opus_encoder_ctl(encoder, OPUS_SET_VBR_CONSTRAINT(0));
    opus_encoder_ctl(encoder, OPUS_SET_LSB_DEPTH(16));
    opus_encoder_ctl(encoder, OPUS_SET_DTX(0));
    opus_encoder_ctl(encoder, OPUS_SET_INBAND_FEC(0));
    opus_encoder_ctl(encoder, OPUS_SET_PACKET_LOSS_PERC(0));

    // Reset ring buffer
    ring_write_pos = 0;
    ring_read_pos = 0;

    Serial.println("Opus encoder initialized successfully");
    Serial.printf("  Sample rate: %d Hz\n", MIC_SAMPLE_RATE);
    Serial.printf("  Bitrate: %d bps\n", OPUS_BITRATE);
    Serial.printf("  Frame size: %d samples (%d ms)\n", OPUS_FRAME_SAMPLES, OPUS_FRAME_SAMPLES * 1000 / MIC_SAMPLE_RATE);

    return true;
}

void opus_set_callback(opus_encoded_handler callback)
{
    encoded_callback = callback;
}

int opus_receive_pcm(int16_t *data, size_t samples)
{
    if (pcm_ring_buffer == nullptr) {
        return -1;
    }
    for (size_t i = 0; i < samples; i++) {
        size_t next_write = (ring_write_pos + 1) % AUDIO_RING_BUFFER_SAMPLES;
        if (next_write == ring_read_pos) {
            // Buffer full, drop oldest sample
            ring_read_pos = (ring_read_pos + 1) % AUDIO_RING_BUFFER_SAMPLES;
        }
        pcm_ring_buffer[ring_write_pos] = data[i];
        ring_write_pos = next_write;
    }
    return 0;
}

static size_t ring_buffer_available()
{
    if (ring_write_pos >= ring_read_pos) {
        return ring_write_pos - ring_read_pos;
    } else {
        return AUDIO_RING_BUFFER_SAMPLES - ring_read_pos + ring_write_pos;
    }
}

int opus_encode_frame(int16_t *pcm_data, size_t samples)
{
    if (encoder == nullptr || opus_output_buffer == nullptr) {
        return -1;
    }

    if (samples != OPUS_FRAME_SAMPLES) {
        Serial.printf("Invalid frame size: %d (expected %d)\n", samples, OPUS_FRAME_SAMPLES);
        return -1;
    }

    opus_int32 encoded_bytes =
        opus_encode(encoder, pcm_data, OPUS_FRAME_SAMPLES, opus_output_buffer, OPUS_OUTPUT_MAX_BYTES);

    if (encoded_bytes < 0) {
        Serial.printf("Opus encoding error: %d\n", encoded_bytes);
        return -1;
    }

    return encoded_bytes;
}

void opus_process()
{
    if (encoder == nullptr || pcm_ring_buffer == nullptr || opus_input_buffer == nullptr) {
        return;
    }

    // Check if we have enough samples for a frame
    while (ring_buffer_available() >= OPUS_FRAME_SAMPLES) {
        // Read samples from ring buffer
        for (size_t i = 0; i < OPUS_FRAME_SAMPLES; i++) {
            opus_input_buffer[i] = pcm_ring_buffer[ring_read_pos];
            ring_read_pos = (ring_read_pos + 1) % AUDIO_RING_BUFFER_SAMPLES;
        }

        // Encode frame
        int encoded_bytes = opus_encode_frame(opus_input_buffer, OPUS_FRAME_SAMPLES);

        if (encoded_bytes > 0 && encoded_callback != nullptr) {
            encoded_callback(opus_output_buffer, encoded_bytes);
        }
    }
}

uint8_t opus_get_codec_id()
{
    // Codec ID 20 = Opus (matching Omi protocol)
    // Actually Omi uses CODEC_ID 21 for Opus
    return AUDIO_CODEC_ID;
}
