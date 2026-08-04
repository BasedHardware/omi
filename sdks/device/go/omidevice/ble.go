package omidevice

import (
	"context"
	"errors"
	"time"
)

// ErrBLEDisabled is returned by Scan/Listen/ReadCodec when the package was
// built without the `ble` build tag (default). Enable with:
//
//	go test -tags ble ./...
//	go build -tags ble ./...
//
// Backend: tinygo.org/x/bluetooth (CoreBluetooth on darwin, BlueZ on linux).
// Chosen over go-ble/ble and paypal/gatt because it compiles cleanly on
// darwin/arm64 desktop without extra CGO toolchains.
var ErrBLEDisabled = errors.New("omidevice: BLE disabled; rebuild with -tags ble")

// Device is a discovered BLE peripheral (Python print_devices surface).
type Device struct {
	ID   string // adapter address / CoreBluetooth identifier string
	Name string
	RSSI int16
}

// Scan discovers nearby BLE devices for up to timeout (or ctx deadline).
// Requires -tags ble; otherwise returns ErrBLEDisabled.
func Scan(ctx context.Context, timeout time.Duration) ([]Device, error) {
	return scan(ctx, timeout)
}

// Listen connects to deviceID and invokes onPacket for each raw audio notify
// (Python listen_to_omi). Blocks until ctx is done. Requires -tags ble.
func Listen(ctx context.Context, deviceID string, onPacket func([]byte)) error {
	return listen(ctx, deviceID, onPacket, false)
}

// ListenPayload is Listen with StripPacketHeader applied to each notify.
func ListenPayload(ctx context.Context, deviceID string, onPayload func([]byte)) error {
	return listen(ctx, deviceID, onPayload, true)
}

// ReadCodec connects and reads the AudioCodec characteristic (first byte = CodecID).
// Requires -tags ble.
func ReadCodec(ctx context.Context, deviceID string) (CodecID, error) {
	return readCodec(ctx, deviceID)
}
