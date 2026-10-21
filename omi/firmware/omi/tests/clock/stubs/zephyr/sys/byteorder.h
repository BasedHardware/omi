#ifndef Z_STUB_BYTEORDER_H
#define Z_STUB_BYTEORDER_H

#include <stdint.h>
#include <string.h>

static inline void sys_put_be16(uint16_t val, uint8_t dst[2])
{
    dst[0] = (uint8_t) (val >> 8);
    dst[1] = (uint8_t) val;
}
static inline void sys_put_be32(uint32_t val, uint8_t dst[4])
{
    dst[0] = (uint8_t) (val >> 24);
    dst[1] = (uint8_t) (val >> 16);
    dst[2] = (uint8_t) (val >> 8);
    dst[3] = (uint8_t) val;
}
static inline void sys_put_be64(uint64_t val, uint8_t dst[8])
{
    for (int i = 0; i < 8; i++) {
        dst[i] = (uint8_t) (val >> (56 - 8 * i));
    }
}
static inline uint16_t sys_get_be16(const uint8_t src[2])
{
    return (uint16_t) ((src[0] << 8) | src[1]);
}
static inline uint32_t sys_get_be32(const uint8_t src[4])
{
    return ((uint32_t) src[0] << 24) | ((uint32_t) src[1] << 16) | ((uint32_t) src[2] << 8) | src[3];
}
static inline uint64_t sys_get_be64(const uint8_t src[8])
{
    uint64_t v = 0;
    for (int i = 0; i < 8; i++) {
        v = (v << 8) | src[i];
    }
    return v;
}

#endif
