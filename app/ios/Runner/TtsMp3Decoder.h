#ifndef TtsMp3Decoder_h
#define TtsMp3Decoder_h

#include <stddef.h>

int omi_decode_mp3(const unsigned char *bytes, int length, int *channels,
                   int *sample_rate, int *samples_per_channel, short **pcm);
void omi_free_decoded_audio(void *buffer);

#endif
