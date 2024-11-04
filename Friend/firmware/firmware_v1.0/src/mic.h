#ifndef MIC_H
#define MIC_H

#include <stdint.h>

// Add voice configuration
#define VOICE_GAIN 0x50  // Adjusted gain for voice capture

// Existing declarations...
typedef void (*mix_handler)(int16_t *data);
void set_mic_callback(mix_handler callback);
int mic_start(void);

// Change return type to int
int mic_configure_for_voice(void);

#endif
