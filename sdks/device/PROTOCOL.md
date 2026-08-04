# Omi Device BLE Protocol

Shared contract for device SDKs (`sdks/python`, `sdks/swift`, `sdks/react-native`, `sdks/device/*`).

## GATT

| Role | UUID |
|------|------|
| Omi service | `19b10000-e8f2-537e-4f6c-d104768a1214` |
| Audio data stream (notify) | `19b10001-e8f2-537e-4f6c-d104768a1214` |
| Audio codec (read) | `19b10002-e8f2-537e-4f6c-d104768a1214` |
| Battery service | `0000180f-0000-1000-8000-00805f9b34fb` |
| Battery level | `00002a19-0000-1000-8000-00805f9b34fb` |

## Codec IDs (first byte of codec characteristic)

| ID | Codec |
|----|-------|
| 0 | PCM 16-bit |
| 1 | PCM 8-bit |
| 20 / `0x14` | Opus (common on Friend/Omi) |

Default stream assumption in thin SDKs: **Opus @ 16 kHz mono**, frame size **960 samples**.

## Audio packet framing

Notify payload on audio data characteristic:

```
[3-byte header][codec payload...]
```

Device SDKs strip the first **3 bytes** before Opus/PCM decode (matches `sdks/python/omi/decoder.py`).

## Sample rate

PCM output: **16-bit little-endian mono @ 16_000 Hz**.

Header size and codec map are firmware-coupled — change here and in every device SDK together.
