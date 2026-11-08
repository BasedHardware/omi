//
//  WearableDeviceRegistry.swift
//  PALApp
//
//  Created by Eric Bariaux on 03/07/2024.
//

import CoreBluetooth
import Foundation

class WearableDeviceRegistry {
    static let shared = WearableDeviceRegistry()
    
    private init() { }
    
    private var wearableRegistry: [WearableDevice.Type] = []
    private(set) var scanServices: [CBUUID] = []

    enum RegistryError: Error {
        case duplicateScanUUID
    }

    func registerDevice(wearable: WearableDevice.Type) throws {
        if scanServices.contains(wearable.deviceConfiguration.scanServiceUUID) {
            throw RegistryError.duplicateScanUUID
        }
        wearableRegistry.append(wearable)
        scanServices.append(wearable.deviceConfiguration.scanServiceUUID)
    }
    
    func deviceTypeForService(uuid serviceUUID: CBUUID) -> WearableDevice.Type? {
        return  wearableRegistry.first(where: { $0.deviceConfiguration.scanServiceUUID == serviceUUID })
    }

    func deviceTypeForReference(_ reference: WearableDevice.DeviceReference) -> WearableDevice.Type? {
        return  wearableRegistry.first(where: { $0.deviceConfiguration.reference == reference })
    }
    
}
