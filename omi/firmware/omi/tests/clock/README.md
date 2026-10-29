# Recording clock host regression

Run from the repository root:

```sh
make -C omi/firmware/omi/tests/clock run
make -C omi/firmware/omi/tests/clock run BUILD_DIR=build/sanitize \
  CFLAGS='-std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-variable -pthread -fsanitize=address,undefined -fno-omit-frame-pointer'
```

On the managed Omi workspace host, wrap these commands in `bin/omi-heavy run --`.
Build output stays in the ignored `build/` directory (inside the task worktree).

The harness compiles production `rtc.c`, `sd_card.c` and `storage.c` together. It checks
unset/zero-uptime capture, settings restore after downtime, IMU restore, phone
sync within a batch, bad-clock fallback and epoch bounds, payload preservation
through media commit/readback, live GATT status without cache refresh, and trust
revocation on a second boot. A concurrent
restore/sync writer exercises the atomic timestamp/trust snapshot with real
pthread mutexes. The fake media and scheduler do not prove Zephyr scheduling,
real SD durability, or end-to-end app behavior; hardware validation is required.

The minimal Zephyr stubs are adapted from draft #20450's host harness, isolated
here to avoid changing its custody tests or APIs. No custody implementation is
imported. When integrating #20450, replace its valid-RTC timestamp selection with
`rtc_get_record_timestamp()` and use `rtc_is_trusted()` for status reads. Keep
its durability, reclaim and live-mark logic intact.

The ring timestamp stays `[u32 BE][440 audio bytes]`. Bit 31 denotes uptime;
the low 31 bits are seconds since boot at SD-worker dequeue. Restored diagnostic
epochs never enter the recording stream. Compatibility filenames for flagged
records use `00000000.txt` (missing time), rather than exposing uptime as UTC.
There is no separate SD timestamp-marker stream in the current CV1 writer.
