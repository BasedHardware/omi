#include "TtsMp3Decoder.h"

#include <limits.h>
#include <stdlib.h>
#include <string.h>

#define MINIMP3_NO_SIMD
#define MINIMP3_IMPLEMENTATION
#include "NativeVendor/minimp3.h"

int omi_decode_mp3(const unsigned char *bytes, int length, int *channels,
                   int *sample_rate, int *samples_per_channel, short **pcm) {
  mp3dec_t decoder;
  mp3dec_init(&decoder);

  short *output = NULL;
  size_t count = 0;
  size_t capacity = 0;
  int stream_channels = 0;
  int stream_rate = 0;
  mp3d_sample_t frame_pcm[MINIMP3_MAX_SAMPLES_PER_FRAME];
  mp3dec_frame_info_t info;
  const unsigned char *cursor = bytes;
  int remaining = length;

  while (remaining > 0) {
    const int frame_samples =
        mp3dec_decode_frame(&decoder, cursor, remaining, frame_pcm, &info);
    if (info.frame_bytes <= 0) break;
    if (frame_samples > 0) {
      stream_channels = info.channels;
      stream_rate = info.hz;
      const size_t produced = (size_t)frame_samples * (size_t)info.channels;
      const size_t needed = count + produced;
      if (needed > capacity) {
        size_t grown_capacity = capacity == 0 ? 16384 : capacity;
        while (grown_capacity < needed) grown_capacity *= 2;
        short *grown = (short *)realloc(output, grown_capacity * sizeof(short));
        if (grown == NULL) {
          free(output);
          return 1;
        }
        output = grown;
        capacity = grown_capacity;
      }
      memcpy(output + count, frame_pcm, produced * sizeof(short));
      count += produced;
    }
    cursor += info.frame_bytes;
    remaining -= info.frame_bytes;
  }

  if (output == NULL || stream_channels <= 0) {
    free(output);
    return 1;
  }
  const size_t per_channel = count / (size_t)stream_channels;
  if (per_channel > INT_MAX) {
    free(output);
    return 1;
  }
  *channels = stream_channels;
  *sample_rate = stream_rate;
  *samples_per_channel = (int)per_channel;
  *pcm = output;
  return 0;
}

void omi_free_decoded_audio(void *buffer) { free(buffer); }
