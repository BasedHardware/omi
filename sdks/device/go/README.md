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


### Drain deepgram results before closing the stream

Deepgram `Stop()` sends `CloseStream`, waits up to five seconds for final transcript delivery, and then closes the connection. Audio writes and the shutdown frame each have a five-second write deadline, so a stalled audio write cannot hold shutdown indefinitely. Errors are returned to the caller. Parakeet retains its plain `finalize` frame. Run `go test -race ./...` for the hardware-free suite; repository preflight selects it for SDK changes.

### Limitations

- Needs Bluetooth permission/adapter; CI and headless hosts stay on default build.
- macOS device IDs are CoreBluetooth identifiers (not always classic MACs).
- `ReadCodec` relies on GATT Read; may fail if characteristic is notify-only on some firmware.
