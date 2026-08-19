# 3.0.21+56 host regression

This pure-C test covers the two new capture boundaries:

- stateful 8 kHz stereo to 16 kHz mono interpolation across DMA blocks; and
- software-VAD quiet/active transitions, bounded pre-roll ordering, metrics,
  and fail-open behavior after a codec emit error.

Run from `omi/firmware/omi`:

```sh
cc -std=c11 -Wall -Wextra -Werror \
  -Isrc \
  src/audio_frontend.c src/software_vad.c tests/plus56/test_plus56.c \
  -o /tmp/omi-plus56-host-test
/tmp/omi-plus56-host-test
```
