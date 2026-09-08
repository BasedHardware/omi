//go:build ble

package omidevice

import (
	"context"
	"errors"
	"strings"
	"testing"

	"tinygo.org/x/bluetooth"
)

type matchingAdapter struct {
	address   bluetooth.Address
	connected bool
	noMatch   bool
	scanErr   error
}

func (a *matchingAdapter) Scan(callback func(*bluetooth.Adapter, bluetooth.ScanResult)) error {
	if !a.noMatch && a.scanErr == nil {
		callback(nil, bluetooth.ScanResult{Address: a.address})
	}
	return a.scanErr
}

func TestConnectDoesNotConnectAfterEmptyScan(t *testing.T) {
	adapter := &matchingAdapter{noMatch: true}
	_, err := connect(context.Background(), adapter, "missing-device")
	if err == nil || !strings.Contains(err.Error(), "not found") {
		t.Fatalf("want device not found, got %v", err)
	}
	if adapter.connected {
		t.Fatal("connected without a scan match")
	}
}

func TestConnectPreservesScanError(t *testing.T) {
	scanErr := errors.New("scan failed")
	adapter := &matchingAdapter{scanErr: scanErr}
	_, err := connect(context.Background(), adapter, "device")
	if !errors.Is(err, scanErr) {
		t.Fatalf("want scan error, got %v", err)
	}
	if adapter.connected {
		t.Fatal("connected after a scan error")
	}
}

func (a *matchingAdapter) StopScan() error { return nil }

func (a *matchingAdapter) Connect(address bluetooth.Address, _ bluetooth.ConnectionParams) (bluetooth.Device, error) {
	a.connected = address.String() == a.address.String()
	return bluetooth.Device{}, nil
}

func TestConnectKeepsMatchWhenScanCompletes(t *testing.T) {
	// Each scan reports a matching device and immediately completes. Both events
	// must describe the same successful scan, regardless of receive ordering.
	for i := 0; i < 1000; i++ {
		adapter := &matchingAdapter{}
		adapter.address.Set("00112233-4455-6677-8899-AABBCCDDEEFF")
		_, err := connect(context.Background(), adapter, adapter.address.String())
		if err != nil {
			t.Fatalf("matching scan %d: %v", i, err)
		}
		if !adapter.connected {
			t.Fatal("matching address was not connected")
		}
	}
}
