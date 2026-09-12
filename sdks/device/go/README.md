# Omi Device Go SDK (`omidevice`)

Protocol helpers + optional BLE scan/listen for the Omi wearable.

## Default build (no hardware)

```bash
go test ./...
go test -race ./...
```

The race-enabled suite exercises streaming-transcriber readiness with in-memory
WebSocket connections; it needs no device, API credentials, or network service.
Parakeet ignores PCM until its server sends `ready`, while Deepgram accepts PCM
as soon as its connection is established.

Exports UUIDs, `StripPacketHeader`, STT helpers. `Scan` / `Listen` / `ListenPayload` / `ReadCodec` return `ErrBLEDisabled`.

## BLE build (`-tags ble`)

Uses [`tinygo.org/x/bluetooth`](https://github.com/tinygo-org/bluetooth) (CoreBluetooth on macOS, BlueZ on Linux). Compiles on desktop darwin/arm64.

```bash
go test -tags ble ./...
go run -tags ble ./examples/...   # if present
```

```go
devices, err := omidevice.Scan(ctx, 5*time.Second)
err = omidevice.ListenPayload(ctx, devices[0].ID, func(payload []byte) {
    // Opus/PCM frames with 3-byte header stripped
})
```

Mirrors Python `print_devices` / `listen_to_omi` in `sdks/python/omi/bluetooth.py`.

### Limitations

- Needs Bluetooth permission/adapter; CI and headless hosts stay on default build.
- macOS device IDs are CoreBluetooth identifiers (not always classic MACs).
- `ReadCodec` relies on GATT Read; may fail if characteristic is notify-only on some firmware.

### Local Whisper retries

`NewWhisper` accepts a runner and buffers PCM until a full batch or `Stop()`.
If the runner returns an error, the buffered audio is retained. Retry with
`Stop()`; do not append the audio from that failed flush again. Until `Stop()`
succeeds, `AppendPCM` rejects new chunks without buffering them or invoking the
runner. Those rejections match `errors.Is(err, stt.ErrWhisperPendingAudio)`;
the caller owns the rejected chunks and can submit them after recovery. Pause
the source while retrying so a persistent failure does not accumulate audio.
A successful flush clears the buffer and emits the non-empty transcript once.

The Go Device SDK pull-request workflow checks `gofmt`, runs `go vet ./...`,
and runs `go test -race ./...` for this
module without BLE hardware or live transcription services.
