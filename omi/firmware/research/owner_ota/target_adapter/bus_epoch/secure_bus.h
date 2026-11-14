#ifndef CV1_SECURE_BUS_H
#define CV1_SECURE_BUS_H
#include "storage_adapter.h"
enum cv1_bus_service { CV1_BUS_NOR_READ = 1, CV1_BUS_SD_SECTOR_ZERO = 2 };
struct cv1_bus_ops {
    void *context;
    int (*owned)(void *);      /* continuous enforcement must exist, snapshot alone insufficient */
    uint32_t (*epoch)(void *); /* boot-issued identity, not mutable NS input */
    uint64_t (*millis)(void *);
    int (*whole_read)(void *, enum cv1_bus_service, uint32_t, void *, size_t);
    int (*finish)(void *); /* CS high and DMA/driver quiescent, no forced unlock */
};
struct cv1_secure_bus {
    atomic_flag busy;
    struct cv1_bus_ops ops;
    uint32_t epoch;
    int poisoned;
    _Alignas(32) uint8_t bounce[512];
};
int cv1_bus_init(struct cv1_secure_bus *, struct cv1_bus_ops, uint32_t);
/* Secure-only callers. No source/config pointers from NS; no writes or raw SPI.
 * dst may not alias context/bounce; whole output invalid on error. */
int cv1_bus_read(struct cv1_secure_bus *, uint32_t, enum cv1_bus_service, uint32_t, uint8_t *, size_t);
int cv1_bus_nor_io(void *, unsigned, uint32_t, void *, size_t);
#endif
