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
        print("Did receive read request \(request)")

        if request.characteristic.uuid == Self.audioCodecCharacteristicUUID {
            // 0 = PCM16 / raw — matches simulator mic tap format
            let codec = Data([0])
            guard request.offset <= codec.count else {
                peripheral.respond(to: request, withResult: .invalidOffset)
                return
            }
            request.value = codec.subdata(in: request.offset..<codec.count)
            peripheral.respond(to: request, withResult: .success)
            return
        }

        if let value = request.characteristic.value {
            guard request.offset <= value.count else {
                peripheral.respond(to: request, withResult: .invalidOffset)
                return
            }
            request.value = value.subdata(in: request.offset..<value.count)
            peripheral.respond(to: request, withResult: .success)
            return
        }

        peripheral.respond(to: request, withResult: .attributeNotFound)
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
