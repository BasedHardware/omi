#include <haly/nrfy_gpio.h>

// #define SAMPLE_RATE 16000
#define MIC_GAIN 64
#define MIC_IRC_PRIORITY 7
#define MIC_BUFFER_SAMPLES 1600    // 100ms
#define AUDIO_BUFFER_SAMPLES 16000 // 1s
#define NETWORK_RING_BUF_SIZE 32   // number of frames * CODEC_OUTPUT_MAX_BYTES
#define MINIMAL_PACKET_SIZE 27     // Lowered from 100 to match minimum BLE MTU

// New PDM pin mappings (P1.xx = Port 1)
#define PDM_DIN_PIN NRF_GPIO_PIN_MAP(1, 0)   // P1.00 - PDM_DATA
#define PDM_CLK_PIN NRF_GPIO_PIN_MAP(1, 1)   // P1.01 - PDM_CLK
#define PDM_WAKE_PIN NRF_GPIO_PIN_MAP(1, 2)  // Optional for future use
#define PDM_EN_PIN NRF_GPIO_PIN_MAP(1, 4)    // Optional for future use
#define PDM_THSEL_PIN NRF_GPIO_PIN_MAP(1, 5) // Optional for future use
#define PDM_PWR_PIN NRF_GPIO_PIN_MAP(1, 4)   // Currently using EN as PWR pin

// Codecs
#ifdef CONFIG_OMI_CODEC_OPUS
#define CODEC_OPUS 1
#else
#error "Enable CONFIG_OMI_CODEC_OPUS in the project .conf file"
#endif

#if CODEC_OPUS
#define CODEC_PACKAGE_SAMPLES 160
#define CODEC_OUTPUT_MAX_BYTES CODEC_PACKAGE_SAMPLES * 2 // Let's assume that 16bit is enough
#define CODEC_OPUS_APPLICATION OPUS_APPLICATION_RESTRICTED_LOWDELAY
#define CODEC_OPUS_BITRATE 32000
#define CODEC_OPUS_VBR 1 // Or 1
#define CODEC_OPUS_COMPLEXITY 3
#endif
#define CONFIG_OPUS_MODE CONFIG_OPUS_MODE_CELT

// Codec IDs

#ifdef CODEC_OPUS
#define CODEC_ID 20
#endif

// Logs
// #define LOG_DISCARDED