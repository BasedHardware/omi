package omidevice

import "testing"

func TestStripPacketHeader(t *testing.T) {
	if got := StripPacketHeader([]byte{1, 2}); got != nil {
		t.Fatalf("short packet: %v", got)
	}
	in := []byte{0xaa, 0xbb, 0xcc, 0x01, 0x02, 0x03}
	got := StripPacketHeader(in)
	if len(got) != 3 || got[0] != 0x01 || got[2] != 0x03 {
		t.Fatalf("got %v", got)
	}
	if AudioDataUUID == "" || ServiceUUID == "" {
		t.Fatal("uuids empty")
	}
}
