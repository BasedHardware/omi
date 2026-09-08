//
//  BLEManager.swift
//  OmiSimulator
//
//  Created by Eric Bariaux on 24/05/2024.
//

import Foundation
import CoreBluetooth

class BLEManager: NSObject, ObservableObject {

    var manager: CBPeripheralManager?
    var packetCounter: UInt16 = 0

    @Published var batteryLevel: UInt8 = 87
    @Published var charging: Bool = false
    @Published var ledBrightness: UInt8 = 50
    @Published var microphoneGain: UInt8 = 4

    // Audio (discovery + streaming)
    private static let audioServiceUUID = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
    private static let audioCharacteristicUUID = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
    private static let audioCodecCharacteristicUUID = CBUUID(string: "19B10002-E8F2-537E-4F6C-D104768A1214")

    // Standard Device Information Service (0x180A) — read by RN OmiDeviceInformation
    private static let deviceInformationServiceUUID = CBUUID(string: "180A")
    private static let modelNumberUUID = CBUUID(string: "2A24")
    private static let serialNumberUUID = CBUUID(string: "2A25")
    private static let firmwareRevisionUUID = CBUUID(string: "2A26")
    private static let hardwareRevisionUUID = CBUUID(string: "2A27")
    private static let manufacturerNameUUID = CBUUID(string: "2A29")

    // Standard Battery Service (0x180F) — read + notify by RN
    private static let batteryServiceUUID = CBUUID(string: "180F")
    private static let batteryLevelUUID = CBUUID(string: "2A19")

    // Features bitmask (button | ledBrightness | microphoneGain) — skip storage for this cut
    private static let featuresServiceUUID = CBUUID(string: "19B10020-E8F2-537E-4F6C-D104768A1214")
    private static let featuresCharacteristicUUID = CBUUID(string: "19B10021-E8F2-537E-4F6C-D104768A1214")
    /// bit2=button(4), bit7=led(128), bit8=micGain(256) → 388
    private static let featuresMask: UInt32 = 4 | (1 << 7) | (1 << 8)

    // Button notify (RN enables only when features bit2 set)
    private static let buttonServiceUUID = CBUUID(string: "23ba7924-0000-1000-7450-346eac492e92")
    private static let buttonCharacteristicUUID = CBUUID(string: "23ba7925-0000-1000-7450-346eac492e92")

    // Settings (LED / mic gain / charging)
    private static let settingsServiceUUID = CBUUID(string: "19B10010-E8F2-537E-4F6C-D104768A1214")
    private static let ledCharacteristicUUID = CBUUID(string: "19B10011-E8F2-537E-4F6C-D104768A1214")
    private static let micGainCharacteristicUUID = CBUUID(string: "19B10012-E8F2-537E-4F6C-D104768A1214")
    private static let chargingCharacteristicUUID = CBUUID(string: "19B10013-E8F2-537E-4F6C-D104768A1214")

    private let audioCharacteristic = CBMutableCharacteristic(
        type: BLEManager.audioCharacteristicUUID,
        properties: .notify,
        value: nil,
        permissions: .readable
    )

    private let audioCodecCharacteristic = CBMutableCharacteristic(
        type: BLEManager.audioCodecCharacteristicUUID,
        properties: .read,
        value: nil,
        permissions: .readable
    )

    private let batteryLevelCharacteristic = CBMutableCharacteristic(
        type: BLEManager.batteryLevelUUID,
        properties: [.read, .notify],
        value: nil,
        permissions: .readable
    )

    private let featuresCharacteristic = CBMutableCharacteristic(
        type: BLEManager.featuresCharacteristicUUID,
        properties: .read,
        value: nil,
        permissions: .readable
    )

    private let buttonCharacteristic = CBMutableCharacteristic(
        type: BLEManager.buttonCharacteristicUUID,
        properties: .notify,
        value: nil,
        permissions: .readable
    )

    private let ledCharacteristic = CBMutableCharacteristic(
        type: BLEManager.ledCharacteristicUUID,
        properties: [.read, .write],
        value: nil,
        permissions: [.readable, .writeable]
    )

    private let micGainCharacteristic = CBMutableCharacteristic(
        type: BLEManager.micGainCharacteristicUUID,
        properties: [.read, .write],
        value: nil,
        permissions: [.readable, .writeable]
    )

    private let chargingCharacteristic = CBMutableCharacteristic(
        type: BLEManager.chargingCharacteristicUUID,
        properties: [.read, .notify],
        value: nil,
        permissions: .readable
    )

    private lazy var deviceInfoCharacteristics: [CBMutableCharacteristic] = [
        CBMutableCharacteristic(
            type: Self.modelNumberUUID,
            properties: .read,
            value: Data("Omi Devkit".utf8),
            permissions: .readable
        ),
        CBMutableCharacteristic(
            type: Self.firmwareRevisionUUID,
            properties: .read,
            value: Data("sim-1.0.0".utf8),
            permissions: .readable
        ),
        CBMutableCharacteristic(
            type: Self.hardwareRevisionUUID,
            properties: .read,
            value: Data("mac-simulator".utf8),
            permissions: .readable
        ),
        CBMutableCharacteristic(
            type: Self.manufacturerNameUUID,
            properties: .read,
            value: Data("Based Hardware".utf8),
            permissions: .readable
        ),
        CBMutableCharacteristic(
            type: Self.serialNumberUUID,
            properties: .read,
            value: Data("OMI-SIM-0001".utf8),
            permissions: .readable
        ),
    ]

    func start() {
        manager = CBPeripheralManager(delegate: self, queue: nil)
    }

    func setBatteryLevel(_ level: UInt8) {
        batteryLevel = min(level, 100)
        let data = Data([batteryLevel])
        manager?.updateValue(data, for: batteryLevelCharacteristic, onSubscribedCentrals: nil)
    }

    func setCharging(_ isCharging: Bool) {
        charging = isCharging
        let data = Data([isCharging ? 1 : 0])
        manager?.updateValue(data, for: chargingCharacteristic, onSubscribedCentrals: nil)
    }

    /// Fire an Omi double-press notification (8 bytes: action=2, rest zero).
    func fireDoublePress() {
        let payload = Data([2, 0, 0, 0, 0, 0, 0, 0])
        let ok = manager?.updateValue(payload, for: buttonCharacteristic, onSubscribedCentrals: nil) ?? false
        print(ok ? "Button double-press notified" : "Button double-press queued/failed (no subscriber or full)")
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

extension BLEManager: CBPeripheralManagerDelegate {

    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        print("Peripheral state update \(peripheral.state)")

        if peripheral.state == .poweredOn {
            let audioService = CBMutableService(type: Self.audioServiceUUID, primary: true)
            audioService.characteristics = [audioCharacteristic, audioCodecCharacteristic]
            manager!.add(audioService)

            let deviceInfoService = CBMutableService(type: Self.deviceInformationServiceUUID, primary: true)
            deviceInfoService.characteristics = deviceInfoCharacteristics
            manager!.add(deviceInfoService)

            let batteryService = CBMutableService(type: Self.batteryServiceUUID, primary: true)
            batteryService.characteristics = [batteryLevelCharacteristic]
            manager!.add(batteryService)

            let featuresService = CBMutableService(type: Self.featuresServiceUUID, primary: true)
            featuresService.characteristics = [featuresCharacteristic]
            manager!.add(featuresService)

            let buttonService = CBMutableService(type: Self.buttonServiceUUID, primary: true)
            buttonService.characteristics = [buttonCharacteristic]
            manager!.add(buttonService)

            let settingsService = CBMutableService(type: Self.settingsServiceUUID, primary: true)
            settingsService.characteristics = [ledCharacteristic, micGainCharacteristic, chargingCharacteristic]
            manager!.add(settingsService)

            // Local name helps Android scanRecord.deviceName; on macOS CoreBluetooth often
            // ignores CBAdvertisementDataLocalNameKey and uses the machine name instead.
            // RN v5 discovers by service UUID regardless.
            manager!.startAdvertising([
                CBAdvertisementDataLocalNameKey: "Omi Devkit",
                CBAdvertisementDataServiceUUIDsKey: [Self.audioServiceUUID],
            ])
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
            print("Peripheral added service \(service.uuid)")
        }
    }

    func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveRead request: CBATTRequest) {
        print("Did receive read request \(request.characteristic.uuid)")

        let uuid = request.characteristic.uuid
        let value: Data?

        if uuid == Self.audioCodecCharacteristicUUID {
            value = Data([0]) // PCM16 / raw
        } else if uuid == Self.batteryLevelUUID {
            value = Data([batteryLevel])
        } else if uuid == Self.featuresCharacteristicUUID {
            var mask = Self.featuresMask.littleEndian
            value = withUnsafeBytes(of: &mask) { Data($0) }
        } else if uuid == Self.ledCharacteristicUUID {
            value = Data([ledBrightness])
        } else if uuid == Self.micGainCharacteristicUUID {
            value = Data([microphoneGain])
        } else if uuid == Self.chargingCharacteristicUUID {
            value = Data([charging ? 1 : 0])
        } else if let staticValue = request.characteristic.value {
            value = staticValue
        } else {
            peripheral.respond(to: request, withResult: .attributeNotFound)
            return
        }

        guard let value else {
            peripheral.respond(to: request, withResult: .attributeNotFound)
            return
        }
        guard request.offset <= value.count else {
            peripheral.respond(to: request, withResult: .invalidOffset)
            return
        }
        request.value = value.subdata(in: request.offset..<value.count)
        peripheral.respond(to: request, withResult: .success)
    }

    func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveWrite requests: [CBATTRequest]) {
        for request in requests {
            guard let data = request.value, !data.isEmpty else {
                peripheral.respond(to: request, withResult: .invalidAttributeValueLength)
                return
            }
            let uuid = request.characteristic.uuid
            if uuid == Self.ledCharacteristicUUID {
                let next = data[0]
                guard next <= 100 else {
                    peripheral.respond(to: request, withResult: .invalidAttributeValueLength)
                    return
                }
                DispatchQueue.main.async { self.ledBrightness = next }
            } else if uuid == Self.micGainCharacteristicUUID {
                let next = data[0]
                guard next <= 8 else {
                    peripheral.respond(to: request, withResult: .invalidAttributeValueLength)
                    return
                }
                DispatchQueue.main.async { self.microphoneGain = next }
            } else {
                peripheral.respond(to: request, withResult: .requestNotSupported)
                return
            }
        }
        peripheral.respond(to: requests[0], withResult: .success)
    }
}
