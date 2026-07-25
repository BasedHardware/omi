# Audio storage packer tests

These host-native tests exercise the production frame-to-record packer and ring
transfer integrity helpers without BLE or SD hardware. They enforce that a
rejected SD enqueue cannot consume, duplicate, or reorder the next Opus frame,
pin the CRC32-extended `DONE` notification to golden wire bytes, and cover
power-on reconciliation after transient queue/remount failures.

```sh
cmake -S omi/firmware/omi/tests/audio_storage_packer \
  -B /tmp/omi-audio-storage-packer-tests
cmake --build /tmp/omi-audio-storage-packer-tests
ctest --test-dir /tmp/omi-audio-storage-packer-tests --output-on-failure
```
