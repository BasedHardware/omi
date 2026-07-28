#import "PhoneMicOpusShim.h"

@import OpusKit;

int omi_opus_encoder_set_bitrate(void *encoder, int32_t bitrate) {
    return opus_encoder_ctl((OpusEncoder *)encoder, OPUS_SET_BITRATE_REQUEST, (opus_int32)bitrate);
}
