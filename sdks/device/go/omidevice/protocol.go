// Package omidevice holds Omi wearable BLE protocol helpers.
// BLE scanning/connecting is platform-specific; use smallgo/ble or similar with these UUIDs.
package omidevice

const (
	ServiceUUID     = "19b10000-e8f2-537e-4f6c-d104768a1214"
	AudioDataUUID   = "19b10001-e8f2-537e-4f6c-d104768a1214"
	AudioCodecUUID  = "19b10002-e8f2-537e-4f6c-d104768a1214"
	BatterySvcUUID  = "0000180f-0000-1000-8000-00805f9b34fb"
	BatteryLevelUUID = "00002a19-0000-1000-8000-00805f9b34fb"

	PacketHeaderBytes = 3
	PCMSampleRateHz   = 16000
	OpusFrameSamples  = 960
	PCMChannels       = 1
)

// CodecID is the first byte of the codec characteristic.
type CodecID byte

const (
	CodecPCM16 CodecID = 0
	CodecPCM8  CodecID = 1
	CodecOpus  CodecID = 20
)

// StripPacketHeader removes the 3-byte Omi audio header.
func StripPacketHeader(packet []byte) []byte {
	if len(packet) <= PacketHeaderBytes {
		return nil
	}
	out := make([]byte, len(packet)-PacketHeaderBytes)
	copy(out, packet[PacketHeaderBytes:])
	return out
}
