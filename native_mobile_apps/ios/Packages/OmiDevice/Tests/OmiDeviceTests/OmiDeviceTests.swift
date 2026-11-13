@preconcurrency import CoreBluetooth
import Foundation
@testable import OmiDevice
import Testing

struct OmiGATTTests {
    @Test func stripsThreeByteHeader() throws {
        let packet = Data([0x34, 0x12, 0x00, 0xAA, 0xBB])
        let frame = try #require(OmiGATT.audioPayload(packet))
        #expect(frame.packetID == 0x1234)
        #expect(frame.payload == Data([0xAA, 0xBB]))
        #expect(OmiGATT.audioPayload(Data([0x01, 0x02, 0x03])) == nil)
    }

    @Test func codecMapping() {
        #expect(OmiGATT.Codec(rawValue: 21)?.listenValue == "opus_fs320")
        #expect(OmiGATT.Codec.pcm8.sampleRate == 8000)
        #expect(OmiGATT.Codec.opusFS320.sampleRate == 16000)
    }

    @Test func recognizesOmiAdvertisements() {
        #expect(OmiGATT.isOmi(name: "Omi DevKit 2", advertisedServices: []))
        #expect(OmiGATT.isOmi(name: nil, advertisedServices: [OmiGATT.audioService]))
        #expect(!OmiGATT.isOmi(name: "AirPods", advertisedServices: []))
    }
}

struct PairedDeviceTests {
    /// Shape the Flutter app writes under `flutter.btDevice`.
    @Test func readsFlutterBtDevice() throws {
        let json = #"{"name":"Omi","id":"6F1D0C3A-1B2C-4D5E-8F90-123456789ABC","type":"omi","rssi":-58,"#
            + #""locator":null,"modelNumber":"Omi CV 1","firmwareRevision":"2.0.10"}"#
        let device = try #require(PairedDevice.decode(json))
        #expect(device.name == "Omi")
        #expect(device.firmwareRevision == "2.0.10")
        #expect(PairedDevice.decode(device.encoded)?.id == device.id)
        #expect(PairedDevice.decode("") == nil)
    }
}
