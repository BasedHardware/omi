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

// Codec IDs are firmware-coupled: 20 is DevKit, 21 is Omi CV1 (opusFS320).
func TestCodecIDs(t *testing.T) {
	for _, tc := range []struct {
		name string
		got  CodecID
		want byte
	}{
		{"pcm16", CodecPCM16, 0},
		{"pcm8", CodecPCM8, 1},
		{"opus", CodecOpus, 20},
		{"opusFS320", CodecOpusFS320, 21},
	} {
		if byte(tc.got) != tc.want {
			t.Errorf("%s = %d, want %d", tc.name, tc.got, tc.want)
		}
	}
}
