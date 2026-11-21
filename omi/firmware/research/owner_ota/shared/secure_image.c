#include <string.h>

#include "secure_services.h"
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t) p[0] | ((uint32_t) p[1] << 8) | ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24);
}
int cv1_vectors_valid(uint32_t msp, uint32_t reset, uint32_t size)
{
    return size >= CV1_VECTOR_BYTES && size <= CV1_CAP - CV1_PREFIX && !(msp & 7) && msp >= CV1_STACK_LOW &&
           msp <= CV1_STACK_HIGH && (reset & 1) && reset >= CV1_VTOR + CV1_VECTOR_BYTES && reset < CV1_VTOR + size;
}
int cv1_image_forget(struct cv1_image *i)
{
    if (!i)
        return CV1_EINVAL;
    int rc = 0;
    if (i->lease && i->source.release)
        rc = i->source.release(i->source.context, i->lease);
    volatile uint8_t *p = (volatile uint8_t *) i;
    for (size_t n = 0; n < sizeof(*i); n++)
        p[n] = 0;
    return rc ? CV1_EIO : 0;
}
static int source_read(const struct cv1_image *i, uint32_t off, uint8_t *out, size_t n)
{
    if (!i || !i->lease || !i->source.read || !i->source.check || off > i->size || n > i->size - off)
        return CV1_EINVAL;
    if (i->source.check(i->source.context, i->lease) || i->source.read(i->source.context, i->lease, off, out, n) ||
        i->source.check(i->source.context, i->lease))
        return CV1_EIO;
    return 0;
}
int cv1_image_read(const struct cv1_image *i, uint32_t off, uint8_t *out, size_t n)
{
    if (!i || i->valid != CV1_ADMITTED || !out || off > i->size || n > i->size - off)
        return CV1_EINVAL;
    if (i->source.check(i->source.context, i->lease))
        return CV1_EIO;
    if (off < CV1_PREFIX) {
        size_t take = CV1_PREFIX - off;
        if (take > n)
            take = n;
        memcpy(out, i->prefix + off, take);
        off += (uint32_t) take;
        out += take;
        n -= take;
    }
    return n ? source_read(i, off, out, n) : 0;
}
static int stream_hash(struct cv1_image *i, int payload_only, int vectors, uint8_t digest[32])
{
    struct cv1_digest state, payload;
    memset(&state, 0, sizeof(state));
    memset(&payload, 0, sizeof(payload));
    if (i->crypto.begin(&state))
        return CV1_EAUTH;
    if (!payload_only && i->crypto.begin(&payload)) {
        i->crypto.abort(&state);
        return CV1_EAUTH;
    }
    uint8_t block[512];
    int rc = 0;
    if (!payload_only && i->crypto.update(&state, i->prefix, CV1_PREFIX))
        rc = CV1_EAUTH;
    for (uint32_t off = CV1_PREFIX; !rc && off < i->size;) {
        size_t n = i->size - off;
        if (n > sizeof(block))
            n = sizeof(block);
        rc = source_read(i, off, block, n);
        if (rc)
            break;
        if (vectors && off == CV1_PREFIX) {
            i->msp = get32(block);
            i->reset = get32(block + 4);
            if (!cv1_vectors_valid(i->msp, i->reset, i->payload_size)) {
                rc = CV1_EAUTH;
                break;
            }
            for (unsigned k = 1; k < 85; k++) {
                uint32_t entry = get32(block + k * 4);
                if (entry &&
                    (!(entry & 1) || entry < CV1_VTOR + CV1_VECTOR_BYTES || entry >= CV1_VTOR + i->payload_size)) {
                    rc = CV1_EAUTH;
                    break;
                }
            }
        }
        if (!rc && !vectors && off == CV1_PREFIX && (get32(block) != i->msp || get32(block + 4) != i->reset))
            rc = CV1_EAUTH;
        if (!rc && i->crypto.update(&state, block, n))
            rc = CV1_EAUTH;
        if (!rc && !payload_only && i->crypto.update(&payload, block, n))
            rc = CV1_EAUTH;
        off += (uint32_t) n;
    }
    if (!rc && i->crypto.finish(&state, digest))
        rc = CV1_EAUTH;
    if (!rc && !payload_only) {
        uint8_t hash[32];
        if (i->crypto.finish(&payload, hash) || memcmp(hash, i->prefix + 64, 32))
            rc = CV1_EAUTH;
    }
    i->crypto.abort(&state);
    if (!payload_only)
        i->crypto.abort(&payload);
    return rc;
}
int cv1_image_admit(struct cv1_image *out,
                    uint32_t size,
                    const struct cv1_source *source,
                    const struct cv1_policy *policy,
                    const struct cv1_crypto *crypto)
{
    if (!out)
        return CV1_EINVAL;
    if (!source || !policy || !crypto || !source->acquire || !source->read || !source->check || !source->release ||
        !crypto->sha256 || !crypto->verify || !crypto->begin || !crypto->update || !crypto->finish || !crypto->abort) {
        out->valid = 0;
        return CV1_EINVAL;
    }
    struct cv1_source src = *source;
    struct cv1_policy p = *policy;
    struct cv1_crypto c = *crypto;
    if (cv1_image_forget(out))
        return CV1_EIO;
    if (size < CV1_PREFIX + CV1_VECTOR_BYTES || size > CV1_CAP || p.board != CV1_BOARD || p.abi != CV1_ABI ||
        !p.generation || p.public_key[0] != 4)
        return CV1_EINVAL;
    uint8_t nonzero = 0;
    for (unsigned n = 0; n < 32; n++)
        nonzero |= p.network_hash[n];
    if (!nonzero)
        return CV1_EINVAL;
    out->source = src;
    out->crypto = c;
    out->size = size;
    if (src.acquire(src.context, size, &out->lease) || !out->lease)
        goto invalid;
    if (source_read(out, 0, out->prefix, CV1_PREFIX))
        goto invalid;
    const uint8_t *h = out->prefix;
    out->payload_size = get32(h + 24);
    out->generation = p.generation;
    if (get32(h) != 0x324e574f || get32(h + 4) != 2 || get32(h + 8) != p.board || get32(h + 12) != p.abi ||
        get32(h + 16) != 1 || get32(h + 20) != p.generation || get32(h + 28) != 0 ||
        out->payload_size != size - CV1_PREFIX || memcmp(h + 32, p.network_hash, 32))
        goto invalid;
    for (unsigned n = 192; n < CV1_PREFIX; n++)
        if (h[n])
            goto invalid;
    uint8_t digest[32];
    if (c.sha256(p.public_key, 65, digest) || memcmp(digest, h + 96, 32))
        goto invalid;
    /* Vector metadata is extracted from the SAME chunk fed into payloadSHA,
     * not a separate mutable read. Signature then binds that exact digest. */
    if (stream_hash(out, 1, 1, digest) || memcmp(digest, h + 64, 32))
        goto invalid;
    static const uint8_t domain[] = "CV1-OWNER-APP-v2";
    uint8_t signed_bytes[sizeof(domain) + CV1_HEADER];
    memcpy(signed_bytes, domain, sizeof(domain));
    memcpy(signed_bytes + sizeof(domain), h, CV1_HEADER);
    if (c.sha256(signed_bytes, sizeof(signed_bytes), digest) || c.verify(p.public_key, digest, h + CV1_HEADER))
        goto invalid;
    if (stream_hash(out, 0, 0, out->container_hash) || src.check(src.context, out->lease))
        goto invalid;
    out->valid = CV1_ADMITTED;
    return 0;
invalid: {
    int rc = cv1_image_forget(out);
    return rc ? rc : CV1_EAUTH;
}
}
int cv1_image_intact(const struct cv1_image *input)
{
    if (!input || input->valid != CV1_ADMITTED || input->size < CV1_PREFIX + CV1_VECTOR_BYTES ||
        input->size > CV1_CAP || input->payload_size != input->size - CV1_PREFIX ||
        input->payload_size != get32(input->prefix + 24) || !input->generation ||
        input->generation != get32(input->prefix + 20) ||
        !cv1_vectors_valid(input->msp, input->reset, input->payload_size) || !input->source.check ||
        input->source.check(input->source.context, input->lease))
        return CV1_EAUTH;
    /* stream_hash does not mutate metadata when vectors=0. */
    uint8_t digest[32];
    struct cv1_image *i = (struct cv1_image *) (uintptr_t) input;
    return stream_hash(i, 0, 0, digest) || memcmp(digest, input->container_hash, 32) ? CV1_EAUTH : 0;
}
