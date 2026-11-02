/* Buildable user fixture only. Never deployed or executed by this host demo. */
#include <stdint.h>
void reset(void);
static void fault(void);
__attribute__((used, section(".vectors")))
const uintptr_t vectors[85] = {0x20070000u, (uintptr_t) reset, (uintptr_t) fault, (uintptr_t) fault};
volatile uint32_t user_fixture_state;
void reset(void)
{
    uint32_t (*secure_abi)(void) = (uint32_t (*)(void)) 0x4bfe1u;
    user_fixture_state = secure_abi();
    for (;;)
        __asm__ volatile("wfi");
}
static void fault(void)
{
    for (;;)
        __asm__ volatile("wfi");
}
