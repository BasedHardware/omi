# Harness lane notes (V3 Android emulator)

## Failed teardown must not delete the AVD

`detach` requires the recorded pid **and** ownership marker to prove qemu is
gone before `_delete_avd`. If kill raises, the lease stays un-released, the
AVD is not deleted, and `recover` can retry. An orphaned AVD is better than
deleting the backing store of a process that was not proven dead: the next
`create --force` can collide with a still-running emulator holding the old
name. The same rule applies to the boot-timeout and `adb reverse` failure
paths (`_abort_unbooted_emulator`).

## Adb visibility is not "one emulator at a time"

That limit was what V3 first verified, not a property of qemu or `adb`.
`attach` now ignores physical phones and foreign emulators. It refuses only
when a **harness-owned** AVD whose name is this session's `omi-session-<id>`
is already visible (`adb emu avd name`). Console ports come from the session
port offset and skip serials already in `adb devices`, so two session-owned
AVDs get disjoint serials and disjoint reverse mappings.

## QEMU audio cost (this host, 2026-09-18, loadavg ~10–13)

Baseline was `-no-audio`: first boot 43.07 s, warm 27.65 s, cold `app.started` 970.1 s.

With `-audio wav` + `QEMU_WAV_IN_PATH` pointing at the release-probe WAV:

| Measurement | Seconds | Delta vs `-no-audio` |
|---|---|---|
| Emulator first-boot (incl. AVD create) | 44.55 | +1.48 |
| Emulator warm-boot (same userdata) | 23.23 | −4.42 (noise; not slower) |

Enabling qemu audio did not double the lane. The 4.9 s clip is not the cost. Cold `flutter run` was not re-measured this turn; add ~5 s plus permission/start on top of 970.1 s, not another 970 s.

`adb shell tinycap` is present at `/system/bin/tinycap` but cannot open
`/dev/snd/pcmC0D0c` (`Permission denied` as the unprivileged shell user). That
is not AudioRecord and is not a `platform_mic` receipt. The Omi app's
AudioRecord path still needs a started capture (architect seam or a production
record-control tap).


