#ifndef VAD_GATE_H
#define VAD_GATE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef CONFIG_OMI_ENABLE_VAD_GATE

/* True when the software gate is quiet enough to allow hardware AAD sleep. */
bool vad_gate_allows_hw_aad_sleep(void);

/* Mic resumed from T5838 hardware sleep — forward PCM immediately (no debounce). */
void vad_gate_on_hw_wake(int64_t now_ms);

#else

static inline bool vad_gate_allows_hw_aad_sleep(void)
{
    return true;
}

static inline void vad_gate_on_hw_wake(int64_t now_ms)
{
    (void) now_ms;
}

#endif

#endif /* VAD_GATE_H */
