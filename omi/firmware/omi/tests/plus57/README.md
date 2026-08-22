# 3.0.21+57 host regression

This pure-C test covers the bounded SD batch-read recovery boundary:

- a successful batch uses one multi-sector request;
- the physical failure signature (multi-sector error) switches to checked
  single-sector reads with exact sector and buffer offsets;
- a successful fallback latches CMD17-only reads for later batches in the same
  boot, avoiding repeated failures on a known-bad CMD18/CMD12 path;
- a failed single-sector read stops the fallback and is surfaced; and
- no controller reset, ring mutation, or failed-buffer acceptance is involved.

Run from `omi/firmware/omi`:

```sh
cc -std=c11 -Wall -Wextra -Werror \
  -Isrc \
  src/sd_read_recovery.c tests/plus57/test_plus57.c \
  -o /tmp/omi-plus57-host-test
/tmp/omi-plus57-host-test
```
