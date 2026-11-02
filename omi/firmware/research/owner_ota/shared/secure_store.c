#include <string.h>

#include "secure_services.h"
#define RECORD 256u
#define RAW_RECORD 128u
#define COMMIT 0x434f4d54u
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t) p[0] | ((uint32_t) p[1] << 8) | ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24);
}
static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; i++)
        p[i] = (uint8_t) (v >> (i * 8));
}
static uint32_t crc(const uint8_t *p, size_t n)
{
    uint32_t v = ~0u;
    for (size_t i = 0; i < n; i++) {
        v ^= p[i];
        for (unsigned j = 0; j < 8; j++)
            v = (v >> 1) ^ (0xedb88320u & -(v & 1u));
    }
    return ~v;
}
static int ops(const struct cv1_flash *f)
{
    return f && f->read && f->erase && f->program;
}
static int valid_record(const struct cv1_record *r)
{
    uint8_t h = 0;
    for (unsigned i = 0; i < 32; i++)
        h |= r->hash[i];
    return r->sequence && r->phase >= CV1_COPY && r->phase <= CV1_CONFIRMED &&
           r->size >= CV1_PREFIX + CV1_VECTOR_BYTES && r->size <= CV1_CAP && r->generation && h;
}
static void raw_encode(const struct cv1_record *r, uint8_t b[RAW_RECORD])
{
    memset(b, 0, RAW_RECORD);
    put32(b, 0x314c4e4a);
    put32(b + 4, 1);
    put32(b + 8, (uint32_t) r->sequence);
    put32(b + 12, (uint32_t) (r->sequence >> 32));
    put32(b + 16, r->phase);
    put32(b + 20, r->size);
    put32(b + 24, r->generation);
    memcpy(b + 32, r->hash, 32);
    put32(b + 120, crc(b, 120));
    put32(b + 124, COMMIT);
}
/* Dual-rail bytes make any monotonic incomplete erase either unchanged or
 * invalid: (b,~b) cannot turn into a different valid pair by0->1 only.
 * Programming from verified-erasedFF likewise cannot create another codeword. */
static void encode(const struct cv1_record *r, uint8_t b[RECORD])
{
    uint8_t raw[RAW_RECORD];
    raw_encode(r, raw);
    for (unsigned i = 0; i < RAW_RECORD; i++) {
        b[2 * i] = raw[i];
        b[2 * i + 1] = (uint8_t) ~raw[i];
    }
}
static int decode(const uint8_t encoded[RECORD], struct cv1_record *r)
{
    uint8_t raw[RAW_RECORD];
    for (unsigned i = 0; i < RAW_RECORD; i++) {
        if ((uint8_t) (encoded[2 * i] ^ encoded[2 * i + 1]) != 255)
            return CV1_ESTATE;
        raw[i] = encoded[2 * i];
    }
    const uint8_t *b = raw;
    if (get32(b) != 0x314c4e4a || get32(b + 4) != 1 || get32(b + 124) != COMMIT || get32(b + 120) != crc(b, 120) ||
        get32(b + 28))
        return CV1_ESTATE;
    for (unsigned i = 64; i < 120; i++)
        if (b[i])
            return CV1_ESTATE;
    memset(r, 0, sizeof(*r));
    r->sequence = (uint64_t) get32(b + 8) | ((uint64_t) get32(b + 12) << 32);
    r->phase = get32(b + 16);
    r->size = get32(b + 20);
    r->generation = get32(b + 24);
    memcpy(r->hash, b + 32, 32);
    return valid_record(r) ? 0 : CV1_ESTATE;
}
static int load(const struct cv1_flash *f, struct cv1_record *r, int *slot)
{
    if (!ops(f) || !r)
        return CV1_EINVAL;
    uint8_t a[RECORD], b[RECORD];
    struct cv1_record x, y;
    if (f->read(f->context, CV1_JOURNAL, 0, a, RECORD) || f->read(f->context, CV1_JOURNAL, CV1_PAGE, b, RECORD))
        return CV1_EIO;
    int av = !decode(a, &x), bv = !decode(b, &y);
    if (!av && !bv)
        return CV1_ESTATE;
    if (av && bv) {
        if (x.sequence == y.sequence) {
            if (memcmp(a, b, RECORD))
                return CV1_ESTATE;
        } else if ((x.sequence > y.sequence ? x.sequence - y.sequence : y.sequence - x.sequence) != 1)
            return CV1_ESTATE;
    }
    *slot = av && (!bv || x.sequence >= y.sequence) ? 0 : 1;
    *r = *slot ? y : x;
    return 0;
}
int cv1_journal_load(const struct cv1_flash *f, struct cv1_record *r)
{
    int slot;
    return load(f, r, &slot);
}
int cv1_journal_store(const struct cv1_flash *f, const struct cv1_record *r)
{
    if (!ops(f) || !r || !valid_record(r))
        return CV1_EINVAL;
    struct cv1_record old;
    int slot = 1;
    int rc = load(f, &old, &slot);
    if (rc == CV1_EIO)
        return rc;
    /* Only truly erased first-run pages may initialize. Corrupt/ambiguous
     * journals must not silently restart generation or overwrite evidence. */
    uint8_t check[RECORD];
    if (rc) {
        if (r->sequence != 1)
            return CV1_ESTATE;
        for (uint32_t off = 0; off < CV1_JOURNAL_BYTES; off += sizeof(check)) {
            if (f->read(f->context, CV1_JOURNAL, off, check, sizeof(check)))
                return CV1_EIO;
            for (unsigned i = 0; i < sizeof(check); i++)
                if (check[i] != 255)
                    return CV1_ESTATE;
        }
    } else if (old.sequence == UINT64_MAX || r->sequence != old.sequence + 1)
        return CV1_ESTATE;
    uint32_t target = (uint32_t) (1 - slot) * CV1_PAGE;
    if (f->erase(f->context, CV1_JOURNAL, target, CV1_PAGE))
        return CV1_EIO;
    for (uint32_t off = 0; off < CV1_PAGE; off += sizeof(check)) {
        if (f->read(f->context, CV1_JOURNAL, target + off, check, sizeof(check)))
            return CV1_EIO;
        for (unsigned i = 0; i < sizeof(check); i++)
            if (check[i] != 255)
                return CV1_EIO;
    }
    uint8_t b[RECORD];
    encode(r, b);
    if (f->program(f->context, CV1_JOURNAL, target, b, 248) || f->read(f->context, CV1_JOURNAL, target, check, 248) ||
        memcmp(b, check, 248))
        return CV1_EIO;
    if (f->program(f->context, CV1_JOURNAL, target + 248, b + 248, 8))
        return CV1_EIO;
    if (f->read(f->context, CV1_JOURNAL, target, check, RECORD) || memcmp(b, check, RECORD))
        return CV1_EIO;
    return 0;
}
static int matching(const struct cv1_record *r, const struct cv1_image *i)
{
    return i->valid == CV1_ADMITTED && r->size == i->size && r->generation == i->generation &&
           !memcmp(r->hash, i->container_hash, 32);
}
static int target_matches(const struct cv1_flash *f, const struct cv1_image *i)
{
    struct cv1_digest digest;
    memset(&digest, 0, sizeof(digest));
    if (i->crypto.begin(&digest))
        return CV1_EAUTH;
    uint8_t block[512], hash[32];
    int rc = 0;
    for (uint32_t off = 0; off < i->size;) {
        size_t n = i->size - off;
        if (n > sizeof(block))
            n = sizeof(block);
        if (f->read(f->context, CV1_PERSONAL, off, block, n)) {
            rc = CV1_EIO;
            break;
        }
        if (i->crypto.update(&digest, block, n)) {
            rc = CV1_EAUTH;
            break;
        }
        off += (uint32_t) n;
    }
    if (!rc && (i->crypto.finish(&digest, hash) || memcmp(hash, i->container_hash, 32)))
        rc = CV1_EAUTH;
    i->crypto.abort(&digest);
    return rc;
}

int cv1_copy_verified(const struct cv1_flash *f, const struct cv1_image *i)
{
    if (!ops(f) || cv1_image_intact(i))
        return CV1_EAUTH;
    struct cv1_record old, r;
    int rc = cv1_journal_load(f, &old);
    if (rc == CV1_EIO)
        return rc;
    memset(&r, 0, sizeof(r));
    r.sequence = rc ? 1 : old.sequence + 1;
    if (!rc && old.sequence == UINT64_MAX)
        return CV1_ESTATE;
    r.phase = CV1_COPY;
    r.size = i->size;
    r.generation = i->generation;
    memcpy(r.hash, i->container_hash, 32);
    if ((rc = cv1_journal_store(f, &r)))
        return rc; /* intent durable before erase */
    uint32_t rounded = (i->size + CV1_PAGE - 1) & ~(CV1_PAGE - 1);
    if (rounded > CV1_PERSONAL_BYTES)
        return CV1_EINVAL;
    for (uint32_t off = 0; off < rounded; off += CV1_PAGE)
        if (f->erase(f->context, CV1_PERSONAL, off, CV1_PAGE))
            return CV1_EIO;
    uint8_t chunk[256];
    for (uint32_t off = 0; off < i->size;) {
        size_t n = i->size - off;
        if (n > sizeof(chunk))
            n = sizeof(chunk);
        memset(chunk, 255, sizeof(chunk));
        if ((rc = cv1_image_read(i, off, chunk, n)))
            return rc;
        size_t padded = (n + 3) & ~(size_t) 3;
        if (f->program(f->context, CV1_PERSONAL, off, chunk, padded))
            return CV1_EIO;
        off += (uint32_t) n;
    }
    if ((rc = target_matches(f, i)))
        return rc;
    if (r.sequence == UINT64_MAX)
        return CV1_ESTATE;
    r.sequence++;
    r.phase = CV1_VERIFIED;
    return cv1_journal_store(f, &r);
}
/* Pre-transition phase. Destination is protected by recovery/initial Secure
 * attribution and a single-owner transaction. Small output MUST be outside the
 * large context and remain Secure across final attribution. */
int cv1_prepare_boot(const struct cv1_flash *f, struct cv1_image *i, struct cv1_boot_token *out)
{
    if (!out)
        return CV1_EINVAL;
    if (i) {
        uintptr_t a = (uintptr_t) i, b = (uintptr_t) out;
        if (a > UINTPTR_MAX - sizeof(*i) || b > UINTPTR_MAX - sizeof(*out) ||
            (a < b + sizeof(*out) && b < a + sizeof(*i)))
            return CV1_EINVAL;
    }
    memset(out, 0, sizeof(*out));
    if (!ops(f) || cv1_image_intact(i))
        return CV1_EAUTH;
    struct cv1_record r;
    int rc = cv1_journal_load(f, &r);
    if (rc)
        return rc;
    if (!matching(&r, i) || (r.phase != CV1_VERIFIED && r.phase != CV1_CONFIRMED))
        return CV1_ESTATE;
    if ((rc = target_matches(f, i)))
        return rc;
    struct cv1_boot_token small = {0};
    small.msp = i->msp;
    small.reset = i->reset;
    small.payload_size = i->payload_size;
    small.generation = i->generation;
    small.journal_sequence = r.sequence;
    memcpy(small.hash, i->container_hash, 32);
    /* No future authorization step reads this large context. */
    if (cv1_image_forget(i))
        return CV1_EIO;
    small.valid = CV1_PREPARED;
    *out = small;
    return 0;
}
/* Post-transition phase. No large snapshot reference; final readback must show
 * personalNS RX/noW and protectedS data/NVMC. Never continue across a reset with
 * a prepared in-RAM descriptor: fresh admission is mandatory at each reset. */
int cv1_authorize_boot(const struct cv1_flash *f, struct cv1_boot_token *prepared, struct cv1_boot_token *out)
{
    if (!prepared || !out) {
        if (prepared)
            prepared->valid = 0;
        if (out)
            out->valid = 0;
        return CV1_EINVAL;
    }
    uintptr_t a = (uintptr_t) prepared, b = (uintptr_t) out;
    if (a > UINTPTR_MAX - sizeof(*prepared) || b > UINTPTR_MAX - sizeof(*out) ||
        (a < b + sizeof(*out) && b < a + sizeof(*prepared))) {
        prepared->valid = 0;
        out->valid = 0;
        return CV1_EINVAL;
    }
    struct cv1_boot_token p = *prepared;
    prepared->valid = 0;
    memset(out, 0, sizeof(*out));
    if (!ops(f) || p.valid != CV1_PREPARED || !cv1_vectors_valid(p.msp, p.reset, p.payload_size))
        return CV1_ESTATE;
    struct cv1_record r;
    int rc = cv1_journal_load(f, &r);
    if (rc)
        return rc;
    if (r.sequence != p.journal_sequence || r.generation != p.generation || r.size != p.payload_size + CV1_PREFIX ||
        memcmp(r.hash, p.hash, 32) || (r.phase != CV1_VERIFIED && r.phase != CV1_CONFIRMED))
        return CV1_ESTATE;
    if (!f->isolation_ready || f->isolation_ready(f->context) != 1)
        return CV1_EISOLATION;
    if (r.phase == CV1_VERIFIED) {
        /* Mirror TRIAL on both pages before handoff. One postcommit record-bit
         * fault can then only fall back to anotherTRIAL, never oldVERIFIED. */
        if (r.sequence > UINT64_MAX - 2)
            return CV1_ESTATE;
        r.phase = CV1_TRIAL;
        for (unsigned mirror = 0; mirror < 2; mirror++) {
            r.sequence++;
            if ((rc = cv1_journal_store(f, &r)))
                return rc;
        }
    }
    p.journal_sequence = r.sequence;
    p.valid = CV1_TOKEN;
    *out = p;
    return 0;
}
