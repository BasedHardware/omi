/* Simulator-only hardware queries shared by sim_power.c and stubs.c. */
#ifndef OMI_SIM_HW_H
#define OMI_SIM_HW_H
#include <stdbool.h>

bool omi_sim_button_pressed(void);
bool omi_sim_charging(void);
int omi_sim_battery_mv(void);
bool omi_sim_connected(void);
int omi_sim_sd_state(void);
int omi_sim_sd_ready_ms(void);

/* Provided by the SD model (stubs.c or the linked SD driver seam). */
bool omi_sim_sd_paused(void);
unsigned int omi_sim_sd_mount_attempts(void);
bool omi_sim_sd_ready(void);
unsigned int omi_sim_sd_written(void);
unsigned int omi_sim_sd_dropped(void);
unsigned int omi_sim_sd_gated(void);
unsigned int omi_sim_sd_io_errors(void);
/* True once main() started the (stub) BLE transport. */
bool omi_sim_transport_up(void);
/* stubs.c: deliver one image-management event to the registered mcumgr callback. */
void omi_sim_dfu(int op);

#endif
