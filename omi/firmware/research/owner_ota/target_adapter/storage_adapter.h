/* Secure-only research interface. Never accept this context/ops from NS. */
#ifndef CV1_STORAGE_ADAPTER_H
#define CV1_STORAGE_ADAPTER_H
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#define CV1_BANK_BYTES 0x60000u
#define CV1_BOUNCE 256u
#define CV1_STORAGE_DENIED -1
struct cv1_storage_ops {
    void *context;
    /* Actual attribution + bus/DMA exclusivity + lifecycle evidence required. */
    int (*owned)(void *);
    int (*io)(void *, unsigned, uint32_t, void *, size_t); /* exact bytes or <0 */
};
struct cv1_storage {
    atomic_flag busy;
    struct cv1_storage_ops ops;
    uint64_t epoch, lease;
    uint32_t base, size;
    int poisoned;
    _Alignas(32) uint8_t bounce[CV1_BOUNCE];
};
/* Caller establishes fresh nonzero uint32 boot epoch on each reset. No epoch provider yet. */
int cv1_storage_init(struct cv1_storage *, struct cv1_storage_ops, uint64_t);
int cv1_storage_acquire(struct cv1_storage *, unsigned, uint32_t, uint64_t *);
/* All pointers Secure/nonaliasing. Any failure invalidates ALL dst bytes. */
int cv1_storage_read(struct cv1_storage *, uint64_t, uint32_t, uint8_t *, size_t);
int cv1_storage_check(struct cv1_storage *, uint64_t);
int cv1_storage_release(struct cv1_storage *, uint64_t);
/* Numeric prefilter ONLY; actual CMSE check/copy belongs to a future gateway. */
int cv1_ns_ram_range(uintptr_t, size_t);
/* Fixed range policy; not an internal-flash execution backend. */
int cv1_internal_range(unsigned area, uint32_t offset, size_t length, unsigned op);
int cv1_nor_range(unsigned bank, uint32_t offset, size_t length, unsigned op);
/* Target initializer always refuses: ownership/epoch/driver qualification absent. */
int cv1_target_storage_init(struct cv1_storage *);
#endif
