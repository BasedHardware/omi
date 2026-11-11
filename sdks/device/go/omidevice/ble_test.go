//go:build !ble

package omidevice

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestScanListenDisabledWithoutBLETag(t *testing.T) {
	// Default build (!ble) must not touch the adapter.
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	if _, err := Scan(ctx, 100*time.Millisecond); !errors.Is(err, ErrBLEDisabled) {
		t.Fatalf("Scan: want ErrBLEDisabled, got %v", err)
	}
	if err := Listen(ctx, "aa:bb:cc:dd:ee:ff", func([]byte) {}); !errors.Is(err, ErrBLEDisabled) {
		t.Fatalf("Listen: want ErrBLEDisabled, got %v", err)
	}
	if err := ListenPayload(ctx, "aa:bb:cc:dd:ee:ff", func([]byte) {}); !errors.Is(err, ErrBLEDisabled) {
		t.Fatalf("ListenPayload: want ErrBLEDisabled, got %v", err)
	}
	if _, err := ReadCodec(ctx, "aa:bb:cc:dd:ee:ff"); !errors.Is(err, ErrBLEDisabled) {
		t.Fatalf("ReadCodec: want ErrBLEDisabled, got %v", err)
	}
}
