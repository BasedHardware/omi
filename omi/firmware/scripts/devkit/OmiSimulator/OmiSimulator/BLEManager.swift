import Foundation
import CoreBluetooth
import AVFoundation

enum BleAudioCodec: UInt8, CaseIterable, Identifiable {
    case pcm16 = 0
    case pcm8 = 1
    case mulaw16 = 2
    case mulaw8 = 3
    case opus = 4
    case opusFS320 = 5
    case aac = 6
    case lc3FS1030 = 7
    case unknown = 8

    var id: UInt8 { rawValue }

    var name: String {
        switch self {
        case .pcm16: return "PCM (16kHz)"
        case .pcm8: return "PCM (8kHz)"
        case .mulaw16: return "µ-law (16kHz)"
        case .mulaw8: return "µ-law (8kHz)"
        case .opus: return "OPUS"
        case .opusFS320: return "OPUS (320)"
        case .aac: return "AAC"
        case .lc3FS1030: return "LC3 (10ms/30B)"
        case .unknown: return "Unknown"
        }
    }

    var sampleRate: Double {
        switch self {
        case .pcm16, .opus, .opusFS320, .lc3FS1030: return 16000.0
        case .pcm8, .mulaw8: return 8000.0
        default: return 8000.0
        }
    }

    var pcmFormat: AVAudioCommonFormat {
        return .pcmFormatInt16
    }
}

class BLEManager: NSObject, ObservableObject {

    var manager: CBPeripheralManager?
    var packetCounter: UInt16 = 0

    @Published var selectedCodec: BleAudioCodec = .pcm8 {
        didSet {
            updateCodecCharacteristic()
        }
    }

    private static let audioServiceUUID = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
    private static let audioCharacteristicUUID = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
    private static let audioCodecCharacteristicUUID = CBUUID(string: "19B10002-E8F2-537E-4F6C-D104768A1214")

    private let audioCharacteristic = CBMutableCharacteristic(type: BLEManager.audioCharacteristicUUID, properties: .notify, value: nil, permissions: .readable)
    private let audioCodecCharacteristic = CBMutableCharacteristic(type: BLEManager.audioCodecCharacteristicUUID, properties: .read, value: nil, permissions: .readable)


    func start() {
        manager = CBPeripheralManager(delegate: self, queue: nil)
    }
}

extension BLEManager: CBPeripheralManagerDelegate {

    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        print("Peripheral state update \(peripheral.state)")

        if peripheral.state == .poweredOn {
            updateCodecCharacteristic()
            let audioService = CBMutableService(type: Self.audioServiceUUID, primary: true)
            audioService.characteristics = [audioCharacteristic, audioCodecCharacteristic]

            manager!.add(audioService)

            manager!.startAdvertising([CBAdvertisementDataLocalNameKey : "Friend",
                                   CBAdvertisementDataServiceUUIDsKey : [Self.audioServiceUUID/*, BatteryService.serviceUUID*/]])
        }
    }

    func peripheralManager(
        _ peripheral: CBPeripheralManager,
        didAdd service: CBService,
        error: (any Error)?
    ) {
        if let error {
            print("Peripheral add service error \(error.localizedDescription)")
        } else {
            print("Peripheral services \(peripheral)")
        }
    }

    func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveRead request: CBATTRequest) {
        print("Did receive read request \(request)")
        if request.characteristic.uuid == Self.audioCodecCharacteristicUUID {
            request.value = Data([selectedCodec.rawValue])
            manager?.respond(to: request, withResult: .success)
        }
    }

    private func updateCodecCharacteristic() {
        audioCodecCharacteristic.value = Data([selectedCodec.rawValue])
    }

    func writeAudio(_ data: Data) {
        var packet = withUnsafeBytes(of: UInt16(littleEndian: packetCounter)) { Data($0) }
        if packetCounter == UInt16.max {
            packetCounter = 0
        } else {
            packetCounter += 1
        }
        packet.append(UInt8(0))
        packet.append(data)
        manager?.updateValue(packet, for: audioCharacteristic, onSubscribedCentrals: nil)
    }

}
