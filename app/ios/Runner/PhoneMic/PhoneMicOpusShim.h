#ifndef PHONEMIC_OPUS_SHIM_H
#define PHONEMIC_OPUS_SHIM_H

#include <stdint.h>

/// Non-variadic bridge to `opus_encoder_ctl(enc, OPUS_SET_BITRATE, bitrate)`.
///
/// Swift cannot call C variadic functions at all, so the encoder's bitrate ctl —
/// the only opus call PhoneMicOpusEncoder needs that is variadic — is set through
/// this wrapper. `encoder` is an `OpusEncoder *` passed from Swift as an opaque
/// pointer. Returns the opus status code (OPUS_OK == 0).
int omi_opus_encoder_set_bitrate(void *encoder, int32_t bitrate);

#endif /* PHONEMIC_OPUS_SHIM_H */
