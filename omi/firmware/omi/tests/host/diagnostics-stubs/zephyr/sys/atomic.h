#include <stdatomic.h>
#include <stdint.h>
typedef _Atomic(uint32_t) atomic_t;
#define ATOMIC_INIT(v) (v)
static inline void atomic_set(atomic_t *a, uint32_t v)
{
    atomic_store(a, v);
}
static inline uint32_t atomic_get(atomic_t *a)
{
    return atomic_load(a);
}
static inline void atomic_inc(atomic_t *a)
{
    atomic_fetch_add(a, 1U);
}
