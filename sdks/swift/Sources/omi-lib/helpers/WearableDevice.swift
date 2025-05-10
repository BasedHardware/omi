//
//  WearableDevice.swift
//  PALApp
//
//  Created by Eric Bariaux on 27/04/2024.
//

import Foundation
import CoreBluetooth

class WearableDevice: ObservableObject {
    
    typealias DeviceReference = String
    
    var name: String
    var bleManager: BLEManager
    var id = UUID()
    @Published var status = WearableDeviceStatus.error(message: "Not initialized")
    
    required init(bleManager: BLEManager, name: String) {
        self.bleManager = bleManager
        self.name = name
    }
    
    class var deviceConfiguration: WearableDeviceConfiguration {
        return WearableDeviceConfiguration(reference: "Abstract", scanServiceUUID: CBUUID(), notifyCharacteristicsUUIDs: [])
    }

}

struct WearableDeviceConfiguration {
    /// Name of the device itself (not the individual instance)
    var reference: WearableDevice.DeviceReference
    
    /// UUID of service that identifies the device when scanning for BLE peripherals
    var scanServiceUUID: CBUUID
    
    /// UUID of characterstics for which it wants a notification (from the start)
    var notifyCharacteristicsUUIDs: [CBUUID]
}

enum WearableDeviceStatus {
    case ready
    case error(message: String)
}

protocol BatteryInformation {
    
    var batteryLevel: UInt8 { get }

}

protocol AudioRecordingDevice {

    var isRecording: Bool { get }
    
    func start(recording: Recording)

    func stopRecording()

}

class AudioPacket {
    var packetData = Data()
    var packetNumber: UInt16
    
    init(packetNumber: UInt16) {
        self.packetNumber = packetNumber
    }

    func append(data: Data) {
        packetData.append(data)
    }
}
