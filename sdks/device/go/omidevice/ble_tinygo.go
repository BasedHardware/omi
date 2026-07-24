//go:build ble

package omidevice

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"tinygo.org/x/bluetooth"
)

func scan(ctx context.Context, timeout time.Duration) ([]Device, error) {
	adapter := bluetooth.DefaultAdapter
	if err := adapter.Enable(); err != nil {
		return nil, fmt.Errorf("omidevice: enable adapter: %w", err)
	}

	deadline, ok := ctx.Deadline()
	if !ok {
		if timeout <= 0 {
			timeout = 5 * time.Second
		}
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, timeout)
		defer cancel()
		deadline, _ = ctx.Deadline()
	} else if timeout > 0 {
		// honor the shorter of ctx deadline and timeout
		if t2 := time.Now().Add(timeout); t2.Before(deadline) {
			var cancel context.CancelFunc
			ctx, cancel = context.WithDeadline(ctx, t2)
			defer cancel()
		}
	}

	seen := make(map[string]Device)
	var mu sync.Mutex

	errCh := make(chan error, 1)
	go func() {
		err := adapter.Scan(func(_ *bluetooth.Adapter, res bluetooth.ScanResult) {
			id := res.Address.String()
			mu.Lock()
			seen[id] = Device{ID: id, Name: res.LocalName(), RSSI: res.RSSI}
			mu.Unlock()
		})
		errCh <- err
	}()

	select {
	case <-ctx.Done():
		_ = adapter.StopScan()
		<-errCh
	case err := <-errCh:
		if err != nil {
			return nil, fmt.Errorf("omidevice: scan: %w", err)
		}
	}

	mu.Lock()
	defer mu.Unlock()
	out := make([]Device, 0, len(seen))
	for _, d := range seen {
		out = append(out, d)
	}
	return out, nil
}

func listen(ctx context.Context, deviceID string, onData func([]byte), strip bool) error {
	if onData == nil {
		return fmt.Errorf("omidevice: onPacket/onPayload is nil")
	}
	deviceID = strings.TrimSpace(deviceID)
	if deviceID == "" {
		return fmt.Errorf("omidevice: empty deviceID")
	}

	adapter := bluetooth.DefaultAdapter
	if err := adapter.Enable(); err != nil {
		return fmt.Errorf("omidevice: enable adapter: %w", err)
	}

	dev, err := connect(ctx, adapter, deviceID)
	if err != nil {
		return err
	}
	defer func() { _ = dev.Disconnect() }()

	svcUUID, err := bluetooth.ParseUUID(ServiceUUID)
	if err != nil {
		return fmt.Errorf("omidevice: parse service uuid: %w", err)
	}
	charUUID, err := bluetooth.ParseUUID(AudioDataUUID)
	if err != nil {
		return fmt.Errorf("omidevice: parse audio uuid: %w", err)
	}

	svcs, err := dev.DiscoverServices([]bluetooth.UUID{svcUUID})
	if err != nil {
		return fmt.Errorf("omidevice: discover services: %w", err)
	}
	if len(svcs) == 0 {
		return fmt.Errorf("omidevice: service %s not found", ServiceUUID)
	}

	chars, err := svcs[0].DiscoverCharacteristics([]bluetooth.UUID{charUUID})
	if err != nil {
		return fmt.Errorf("omidevice: discover characteristics: %w", err)
	}
	if len(chars) == 0 {
		return fmt.Errorf("omidevice: characteristic %s not found", AudioDataUUID)
	}

	if err := chars[0].EnableNotifications(func(buf []byte) {
		// copy: stack may reuse notification buffer
		pkt := append([]byte(nil), buf...)
		if strip {
			pkt = StripPacketHeader(pkt)
			if pkt == nil {
				return
			}
		}
		onData(pkt)
	}); err != nil {
		return fmt.Errorf("omidevice: enable notifications: %w", err)
	}

	<-ctx.Done()
	_ = chars[0].EnableNotifications(nil)
	return ctx.Err()
}

func readCodec(ctx context.Context, deviceID string) (CodecID, error) {
	deviceID = strings.TrimSpace(deviceID)
	if deviceID == "" {
		return 0, fmt.Errorf("omidevice: empty deviceID")
	}

	adapter := bluetooth.DefaultAdapter
	if err := adapter.Enable(); err != nil {
		return 0, fmt.Errorf("omidevice: enable adapter: %w", err)
	}

	dev, err := connect(ctx, adapter, deviceID)
	if err != nil {
		return 0, err
	}
	defer func() { _ = dev.Disconnect() }()

	svcUUID, err := bluetooth.ParseUUID(ServiceUUID)
	if err != nil {
		return 0, fmt.Errorf("omidevice: parse service uuid: %w", err)
	}
	codecUUID, err := bluetooth.ParseUUID(AudioCodecUUID)
	if err != nil {
		return 0, fmt.Errorf("omidevice: parse codec uuid: %w", err)
	}

	svcs, err := dev.DiscoverServices([]bluetooth.UUID{svcUUID})
	if err != nil {
		return 0, fmt.Errorf("omidevice: discover services: %w", err)
	}
	if len(svcs) == 0 {
		return 0, fmt.Errorf("omidevice: service %s not found", ServiceUUID)
	}
	chars, err := svcs[0].DiscoverCharacteristics([]bluetooth.UUID{codecUUID})
	if err != nil {
		return 0, fmt.Errorf("omidevice: discover characteristics: %w", err)
	}
	if len(chars) == 0 {
		return 0, fmt.Errorf("omidevice: characteristic %s not found", AudioCodecUUID)
	}

	buf := make([]byte, 16)
	n, err := chars[0].Read(buf)
	if err != nil {
		return 0, fmt.Errorf("omidevice: read codec: %w", err)
	}
	if n < 1 {
		return 0, fmt.Errorf("omidevice: empty codec characteristic")
	}
	return CodecID(buf[0]), nil
}

// connect finds deviceID via a short scan then Connects (matches tinygo examples;
// CoreBluetooth identifiers are not always classic MAC strings).
func connect(ctx context.Context, adapter *bluetooth.Adapter, deviceID string) (bluetooth.Device, error) {
	want := strings.ToLower(deviceID)
	found := make(chan bluetooth.Address, 1)

	scanCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	errCh := make(chan error, 1)
	go func() {
		errCh <- adapter.Scan(func(a *bluetooth.Adapter, res bluetooth.ScanResult) {
			id := strings.ToLower(res.Address.String())
			if id == want || strings.EqualFold(res.LocalName(), deviceID) {
				select {
				case found <- res.Address:
				default:
				}
				_ = a.StopScan()
			}
		})
	}()

	var addr bluetooth.Address
	select {
	case addr = <-found:
		// drain scan exit
		select {
		case <-errCh:
		case <-time.After(2 * time.Second):
		}
	case <-scanCtx.Done():
		_ = adapter.StopScan()
		select {
		case <-errCh:
		case <-time.After(2 * time.Second):
		}
		// last resort: try Address.Set (works when ID is a parseable address)
		addr.Set(deviceID)
	case err := <-errCh:
		if err != nil {
			return bluetooth.Device{}, fmt.Errorf("omidevice: scan for connect: %w", err)
		}
		return bluetooth.Device{}, fmt.Errorf("omidevice: device %q not found", deviceID)
	}

	dev, err := adapter.Connect(addr, bluetooth.ConnectionParams{})
	if err != nil {
		return bluetooth.Device{}, fmt.Errorf("omidevice: connect %s: %w", deviceID, err)
	}
	return dev, nil
}
