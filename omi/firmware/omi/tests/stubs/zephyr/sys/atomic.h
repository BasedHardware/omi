#ifndef Z_STUB_ATOMIC_H
#define Z_STUB_ATOMIC_H

#include <stdbool.h>
#include <stdint.h>

typedef long atomic_t;
typedef long atomic_val_t;

#define ATOMIC_INIT(v) (v)

static inline atomic_val_t atomic_get(const atomic_t *target)
{
    return *target;
}
static inline atomic_val_t atomic_set(atomic_t *target, atomic_val_t value)
{
    atomic_val_t prev = *target;
    *target = value;
    return prev;
}
static inline atomic_val_t atomic_clear(atomic_t *target)
{
    return atomic_set(target, 0);
}
static inline atomic_val_t atomic_inc(atomic_t *target)
{
    return (*target)++;
}
static inline atomic_val_t atomic_add(atomic_t *target, atomic_val_t value)
{
    atomic_val_t prev = *target;
    *target += value;
    return prev;
}
static inline bool atomic_cas(atomic_t *target, atomic_val_t old_value, atomic_val_t new_value)
{
    if (*target == old_value) {
        *target = new_value;
        return true;
    }
    return false;
}

#endif
