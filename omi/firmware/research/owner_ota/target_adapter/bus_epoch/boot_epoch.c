#include "boot_epoch.h"

#include <string.h>
static int reserve_epoch(const struct cv1_flash *f, const uint8_t entropy[32], uint32_t *out)
{
    if (!f || !entropy || !out)
        return -1;
    *out = 0;
    uint8_t present = 0;
    for (unsigned i = 0; i < 32; i++)
        present |= entropy[i];
    if (!present)
        return -1;
    struct cv1_record old, next, readback;
    if (cv1_journal_load(f, &old) || old.generation != CV1_EPOCH_ROLE || old.phase != CV1_CONFIRMED ||
        old.size != 1024 || old.sequence > UINT32_MAX - 2u)
        return -1;
    next = old;
    memcpy(next.hash, entropy, 32);
    /* Both durable advancing records precede issuance. A one-record fallback
     * loses at most one sequence; the next two-step reserve ends strictly
     * above the last issued epoch. Never reseed a corrupt/erased ledger. */
    for (unsigned step = 0; step < 2; step++) {
        next.sequence++;
        if (cv1_journal_store(f, &next) || cv1_journal_load(f, &readback) || readback.sequence != next.sequence ||
            readback.generation != CV1_EPOCH_ROLE || readback.phase != CV1_CONFIRMED || readback.size != 1024 ||
            memcmp(readback.hash, entropy, 32))
            return -1;
    }
    *out = (uint32_t) next.sequence;
    return 0;
}
static atomic_flag reserve_busy = ATOMIC_FLAG_INIT;
int cv1_boot_reserve_epoch(const struct cv1_flash *f, const uint8_t entropy[32], uint32_t *out)
{
    if (!out)
        return -1;
    *out = 0;
    if (atomic_flag_test_and_set_explicit(&reserve_busy, memory_order_acquire))
        return -1;
    int rc = reserve_epoch(f, entropy, out);
    atomic_flag_clear_explicit(&reserve_busy, memory_order_release);
    return rc;
}
int cv1_storage_boot(struct cv1_storage *s,
                     struct cv1_storage_ops ops,
                     const struct cv1_flash *f,
                     const uint8_t entropy[32])
{
    uint32_t epoch;
    if (!s)
        return -1;
    /* Boot-only: invalidate any retained capability before attempting reserve. */
    memset(s, 0, sizeof(*s));
    atomic_flag_clear(&s->busy);
    s->poisoned = 1;
    if (!ops.owned || !ops.io || cv1_boot_reserve_epoch(f, entropy, &epoch))
        return -1;
    return cv1_storage_init(s, ops, epoch);
}
