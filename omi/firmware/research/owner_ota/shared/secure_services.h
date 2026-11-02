/* Production-intended internal Secure services; isolated non-deployable research.
 * NOT NS gateways. Context/policy/ops/token must reside in exclusive Secure RAM.
 * Callbacks are fixed trusted code, never supplied by manifest or NS caller.
 */
#ifndef CV1_SECURE_SERVICES_H
#define CV1_SECURE_SERVICES_H
#include <stddef.h>
#include <stdint.h>
#define CV1_CAP 393216u
#define CV1_PREFIX 512u
#define CV1_HEADER 128u
#define CV1_VECTOR_BYTES 512u
#define CV1_VTOR 0x54200u
#define CV1_STACK_LOW 0x20012100u
#define CV1_STACK_HIGH 0x20070000u
#define CV1_PAGE 4096u
#define CV1_JOURNAL_BYTES 8192u
#define CV1_PERSONAL_BYTES 0x9c000u
#define CV1_BOARD 0x00315643u
#define CV1_ABI 1u
#define CV1_ADMITTED 0x41444d54u
#define CV1_PREPARED 0x50524550u
#define CV1_TOKEN 0x424f4f54u
#define CV1_EINVAL -1
#define CV1_EAUTH -2
#define CV1_EIO -3
#define CV1_ESTATE -4
#define CV1_EISOLATION -5
struct cv1_digest {
    uint64_t opaque[64];
};
struct cv1_crypto {
    int (*sha256)(const uint8_t *, size_t, uint8_t[32]);
    int (*verify)(const uint8_t[65], const uint8_t[32], const uint8_t[64]);
    int (*begin)(struct cv1_digest *);
    int (*update)(struct cv1_digest *, const uint8_t *, size_t);
    int (*finish)(struct cv1_digest *, uint8_t[32]);
    void (*abort)(struct cv1_digest *);
};
/* Fixed approved source bank (candidate or confirmed reference), selected only
 * by the trusted controller. Backend must establish exclusive Secure
 * bus/pin/DMA/storage ownership and deny ALL writers for this lease. A nonce
 * alone does not establish physical immutability. No real backend exists. */
struct cv1_source {
    void *context;
    int (*acquire)(void *, uint32_t, uint64_t *);
    int (*read)(void *, uint64_t, uint32_t, uint8_t *, size_t);
    int (*check)(void *, uint64_t);
    int (*release)(void *, uint64_t);
};
struct cv1_policy {
    uint32_t board, abi, generation;
    uint8_t network_hash[32], public_key[65];
};
/* Small metadata only; payload remains in a Secure-controlled immutable
 * storage lease. Context/callbacks/descriptor/stack must remain Secure. */
struct cv1_image {
    uint8_t prefix[CV1_PREFIX], container_hash[32];
    uint32_t size, payload_size, msp, reset, generation, valid;
    uint64_t lease;
    struct cv1_crypto crypto;
    struct cv1_source source;
};
int cv1_image_admit(struct cv1_image *,
                    uint32_t,
                    const struct cv1_source *,
                    const struct cv1_policy *,
                    const struct cv1_crypto *);
int cv1_image_intact(const struct cv1_image *);
int cv1_image_read(const struct cv1_image *, uint32_t, uint8_t *, size_t);
int cv1_image_forget(struct cv1_image *);
int cv1_vectors_valid(uint32_t, uint32_t, uint32_t);
enum cv1_area { CV1_JOURNAL = 1, CV1_PERSONAL = 2 };
/* Fixed areas, never manifest-supplied addresses. Trial view maps journal to
 * F0000..F2000 and personal to54000..F0000. Host demo reuses ONLY the journal
 * codec through a separately pinned reference view F2000..F4000; it rejects
 * personal access on that view. No real target backend or generic erase API. */
struct cv1_flash {
    void *context;
    int (*read)(void *, enum cv1_area, uint32_t, uint8_t *, size_t);
    int (*erase)(void *, enum cv1_area, uint32_t, size_t);
    int (*program)(void *, enum cv1_area, uint32_t, const uint8_t *, size_t);
    /* Mandatory actual readback of final NS RX/noW + Secure NVMC/TCB ownership.
     * No real backend exists yet. A host fake is not isolation evidence. */
    int (*isolation_ready)(void *);
};
enum cv1_phase { CV1_COPY = 1, CV1_VERIFIED = 2, CV1_TRIAL = 3, CV1_CONFIRMED = 4 };
struct cv1_record {
    uint64_t sequence;
    uint32_t phase, size, generation;
    uint8_t hash[32];
};
struct cv1_boot_token {
    uint32_t valid, msp, reset, payload_size, generation;
    uint64_t journal_sequence;
    uint8_t hash[32];
};
/* Journal CRC detects modeled corruption, NOT malicious Secure writers. */
int cv1_journal_load(const struct cv1_flash *, struct cv1_record *);
int cv1_journal_store(const struct cv1_flash *, const struct cv1_record *);
int cv1_copy_verified(const struct cv1_flash *, const struct cv1_image *);
/* No repeated trial after reset: TRIAL/unknown state returns ESTATE. Fresh
 * admission + destination revalidation required even for confirmed boot. */
int cv1_prepare_boot(const struct cv1_flash *, struct cv1_image *, struct cv1_boot_token *);
int cv1_authorize_boot(const struct cv1_flash *, struct cv1_boot_token *, struct cv1_boot_token *);
extern const struct cv1_crypto cv1_psa_crypto;
#endif
