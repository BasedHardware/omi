//
//  BLEManager.swift
//  FriendSimulator
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
    
    private let audioCharacteristic = CBMutableCharacteristic(type: BLEManager.audioCharacteristicUUID, properties: .notify, value: nil, permissions: .readable)


    func start() {
        manager = CBPeripheralManager(delegate: self, queue: nil)
    }
}

extension BLEManager: CBPeripheralManagerDelegate {
    
    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        print("Peripheral state update \(peripheral.state)")
        
        if peripheral.state == .poweredOn {
            let audioCodecCharacteristic = CBMutableCharacteristic(type: Self.audioCodecCharacteristicUUID, properties: .read, value: nil, permissions: .readable)
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
