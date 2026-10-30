import Foundation
@testable import OmiDevice
import Testing

/// Byte layouts from firmware `lib/core/transport.c`, `haptic.c` and `lib/core/features.h`.
struct OmiControlsTests {
    /// `features_read_handler` on a CV1 build: button, battery, USB, haptic, offline storage,
    /// LED dimming, mic gain (no speaker, no accelerometer) = 0x1FC, as a little-endian `uint32_t`.
    @Test func parsesFeatureBitmask() {
        let features = OmiGATT.Features(Data([0xFC, 0x01, 0x00, 0x00]))
        #expect(features.contains(.button))
        #expect(features.contains(.haptic))
        #expect(features.contains(.offlineStorage))
        #expect(features.contains(.ledDimming))
        #expect(features.contains(.micGain))
        #expect(!features.contains(.speaker))
        #expect(!features.contains(.accelerometer))
        #expect(OmiGATT.Features(Data([0x01, 0x00])).isEmpty)
        #expect(OmiGATT.Features(Data([0x80, 0x00, 0x00, 0x00])) == .ledDimming)
    }

    /// The dim-ratio and mic-gain writes take exactly one byte; firmware caps 100 and 8.
    @Test func encodesSettingsWrites() {
        #expect(OmiGATT.ledBrightnessPayload(42) == Data([42]))
        #expect(OmiGATT.ledBrightnessPayload(150) == Data([100]))
        #expect(OmiGATT.ledBrightnessPayload(-5) == Data([0]))
        #expect(OmiGATT.micGainPayload(5) == Data([5]))
        #expect(OmiGATT.micGainPayload(12) == Data([8]))
        #expect(OmiGATT.micGainPayload(-1) == Data([0]))
    }

    @Test func readsSettingsAndCharging() {
        #expect(OmiGATT.settingValue(Data([0x64])) == 100)
        #expect(OmiGATT.settingValue(Data()) == nil)
        #expect(OmiGATT.isCharging(Data([0x01])) == true)
        #expect(OmiGATT.isCharging(Data([0x00])) == false)
        #expect(OmiGATT.isCharging(Data()) == nil)
    }

    /// `haptic_write_handler`: 1 → 100 ms, 2 → 300 ms, 3 → 500 ms; Find my Omi is three long ones.
    @Test func encodesHaptics() {
        #expect(OmiGATT.Haptic.short.payload == Data([1]))
        #expect(OmiGATT.Haptic.medium.payload == Data([2]))
        #expect(OmiGATT.Haptic.long.payload == Data([3]))
        #expect(OmiGATT.findPattern == [.long, .long, .long])
        #expect(OmiGATT.Control.haptic.characteristic == OmiGATT.haptic)
        #expect(OmiGATT.Control.ledBrightness.characteristic == OmiGATT.ledDimRatio)
    }

    /// DIS 0x2A25: only a 16-hex-digit FICR id counts (`omi_connection.dart` `parseSerialNumber`).
    @Test func parsesSerialNumber() {
        #expect(OmiGATT.serialNumber(Data("0a1b2c3d4e5f6789\u{0}".utf8)) == "0A1B2C3D4E5F6789")
        #expect(OmiGATT.serialNumber(Data(" 0A1B2C3D4E5F6789 ".utf8)) == "0A1B2C3D4E5F6789")
        #expect(OmiGATT.serialNumber(Data("unknown".utf8)) == nil)
        #expect(OmiGATT.serialNumber(Data("FFFFFFFFFFFFFFFF".utf8)) == nil)
        #expect(OmiGATT.serialNumber(Data("0A1B2C3D4E5F67".utf8)) == nil)
        #expect(OmiGATT.serialNumber(Data()) == nil)
    }

    @Test func pairedDeviceKeepsSerial() throws {
        let json = #"{"name":"Omi","id":"6F1D0C3A-1B2C-4D5E-8F90-123456789ABC","type":"omi","rssi":-58,"serialNumber":"0A1B2C3D4E5F6789"}"#
        let device = try #require(PairedDevice.decode(json))
        #expect(device.serialNumber == "0A1B2C3D4E5F6789")
        #expect(PairedDevice.decode(device.encoded)?.serialNumber == "0A1B2C3D4E5F6789")
    }
}
