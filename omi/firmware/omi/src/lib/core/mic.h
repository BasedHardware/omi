#ifndef MIC_H
#define MIC_H

#include <stdbool.h>
#include <stdint.h>

typedef void (*mix_handler)(int16_t *);

/**
 * @brief Initialize the Microphone
 *
 * Initializes the Microphone
 *
 * @return 0 if successful, negative errno code if error
 */
int mic_start();
void set_mic_callback(mix_handler _callback);

void mic_off();
void mic_on();
void mic_pause();
void mic_resume();
typedef enum {
    OMI_POWER_CMD_ACTIVE = 0x00,
    OMI_POWER_CMD_POWER_OFF = 0x01,
    OMI_POWER_CMD_PAUSE_MIC = 0x02,
} omi_power_cmd_t;

bool mic_is_running();
bool mic_is_paused(void);
void mic_set_gain(uint8_t gain_level);

/* True while the mic is in hardware AAD sleep (mic off, waiting for sound).
 * Lets other subsystems (e.g. the status LED) drop to their lowest-power state. */
bool mic_in_aad_sleep(void);
#endif
