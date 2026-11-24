#ifndef TEST_NRF_RESET_H
#define TEST_NRF_RESET_H
#include <stdint.h>
#define NRF_RESET 0
#define NRF_RESET_RESETREAS_DOG0_MASK (1u << 1)
#define NRF_RESET_RESETREAS_DOG1_MASK (1u << 2)
#define NRF_RESET_RESETREAS_LOCKUP_MASK (1u << 3)
#define NRF_RESET_RESETREAS_SREQ_MASK (1u << 4)
#define NRF_RESET_RESETREAS_RESETPIN_MASK (1u << 5)
#define NRF_RESET_RESETREAS_OFF_MASK (1u << 6)
uint32_t nrf_reset_resetreas_get(int);
void nrf_reset_resetreas_clear(int, uint32_t);
#endif
