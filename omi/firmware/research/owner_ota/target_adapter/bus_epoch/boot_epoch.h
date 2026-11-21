#ifndef CV1_BOOT_EPOCH_H
#define CV1_BOOT_EPOCH_H
#include "source_binding.h"
#define CV1_EPOCH_ROLE 0x45504f43u
/* Fixed Secure boot-only journal view, NEVER app/reference journal. Must already
 * contain a provisioned role record; no automatic first-run initialization.
 * Entropy is boot-provided evidence, NOT credential/key material or uniqueness
 * proof. Persistent monotonic reservation provides uniqueness until exhaustion.
 * Single boot authority, no concurrent reserve/reset while services exist. */
int cv1_boot_reserve_epoch(const struct cv1_flash *, const uint8_t entropy[32], uint32_t *);
int cv1_storage_boot(struct cv1_storage *, struct cv1_storage_ops, const struct cv1_flash *, const uint8_t[32]);
#endif
