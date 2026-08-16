//go:build !ble

package omidevice

import (
	"context"
	"time"
)

func scan(context.Context, time.Duration) ([]Device, error) {
	return nil, ErrBLEDisabled
}

func listen(context.Context, string, func([]byte), bool) error {
	return ErrBLEDisabled
}

func readCodec(context.Context, string) (CodecID, error) {
	return 0, ErrBLEDisabled
}
