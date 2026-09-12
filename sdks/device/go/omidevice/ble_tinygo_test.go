//go:build ble

package omidevice

import (
	"context"
	"errors"
	"strings"
	"testing"

	"tinygo.org/x/bluetooth"
)

type fakeConnectAdapter struct {
	address   bluetooth.Address
	connected bool
	skipMatch bool
	scanErr   error
}

func (a *fakeConnectAdapter) Scan(callback func(*bluetooth.Adapter, bluetooth.ScanResult)) error {
	if !a.skipMatch && a.scanErr == nil {
		callback(nil, bluetooth.ScanResult{Address: a.address})
	}
	return a.scanErr
}

func (a *fakeConnectAdapter) StopScan() error { return nil }

func (a *fakeConnectAdapter) Connect(address bluetooth.Address, _ bluetooth.ConnectionParams) (bluetooth.Device, error) {
	a.connected = strings.EqualFold(address.String(), a.address.String())
	return bluetooth.Device{}, nil
}

func TestConnectKeepsMatchWhenScanReturnsImmediately(t *testing.T) {
	const id = "00112233-4455-6677-8899-aabbccddeeff"
	for i := 0; i < 1000; i++ {
		adapter := &fakeConnectAdapter{}
		adapter.address.Set(id)
		if _, err := connect(context.Background(), adapter, id); err != nil {
			t.Fatalf("iteration %d: %v", i, err)
		}
		if !adapter.connected {
			t.Fatalf("iteration %d: scan match was discarded", i)
		}
	}
}

func TestConnectReportsMissingDevice(t *testing.T) {
	adapter := &fakeConnectAdapter{skipMatch: true}
	_, err := connect(context.Background(), adapter, "missing-device")
	if err == nil || !strings.Contains(err.Error(), "not found") {
		t.Fatalf("got %v", err)
	}
	if adapter.connected {
		t.Fatal("connected without a scan match")
	}
}

func TestConnectSurfacesScanError(t *testing.T) {
	scanErr := errors.New("adapter offline")
	adapter := &fakeConnectAdapter{scanErr: scanErr}
	_, err := connect(context.Background(), adapter, "device")
	if !errors.Is(err, scanErr) {
		t.Fatalf("got %v", err)
	}
	if adapter.connected {
		t.Fatal("connected after scan error")
	}
}
