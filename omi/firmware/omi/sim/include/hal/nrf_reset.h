/* Simulator reset-register shim. Bit positions follow the nRF5340 application
 * core RESETREAS register; the value comes from the scenario runner's power
 * model (sim_power.c), not from hardware. */
#ifndef OMI_SIM_NRF_RESET_H
#define OMI_SIM_NRF_RESET_H
#include <stdint.h>

#define NRF_RESET 0
#define NRF_RESET_RESETREAS_RESETPIN_MASK (1u << 0)
#define NRF_RESET_RESETREAS_DOG0_MASK (1u << 1)
#define NRF_RESET_RESETREAS_CTRLAP_MASK (1u << 2)
#define NRF_RESET_RESETREAS_SREQ_MASK (1u << 3)
#define NRF_RESET_RESETREAS_LOCKUP_MASK (1u << 4)
#define NRF_RESET_RESETREAS_OFF_MASK (1u << 5)
#define NRF_RESET_RESETREAS_LPCOMP_MASK (1u << 6)
#define NRF_RESET_RESETREAS_DIF_MASK (1u << 7)
#define NRF_RESET_RESETREAS_DOG1_MASK (1u << 25)
#define NRF_RESET_RESETREAS_VBUS_MASK (1u << 26)

uint32_t nrf_reset_resetreas_get(int reg);
void nrf_reset_resetreas_clear(int reg, uint32_t mask);
#endif
