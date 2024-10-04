//
//  BLEScanner.swift
//  PALApp
//
//  Created by Eric Bariaux on 04/07/2024.
//

import CoreBluetooth
import Foundation


struct DiscoveredDevice: Identifiable, Hashable {
    var name: String
    var deviceIdentifier: UUID
    var deviceType: UserDeviceType
    
    var id: UUID {
        deviceIdentifier
    }
}

@Observable
class BLEScanner : NSObject {
    init(deviceRegistry: WearableDeviceRegistry) {
        self.deviceRegistry = deviceRegistry
        super.init()
        manager = CBCentralManager(delegate: self, queue: nil)
    }
    
    var status: BLEStatus = .off
    
    private var deviceRegistry: WearableDeviceRegistry

    private var manager: CBCentralManager!

    private var peripheral: CBPeripheral?

    var discoveredPeripheralsMap: [UUID: CBPeripheral] = [:]
    
    var discoveredDevicesMap: [UUID: DiscoveredDevice] = [:]
    var discoveredDevices: [DiscoveredDevice] {
        discoveredDevicesMap.values.sorted { $0.name < $1.name }
    }
    
    func stopScanning() {
        manager.stopScan()
        status = .off
    }
}

extension BLEScanner : CBCentralManagerDelegate {
    
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn {
            manager.scanForPeripherals(withServices: deviceRegistry.scanServices)
            status = .scanning
        } else {
            status = .off
        }
    }
    
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        
        print("Discovered \(peripheral.identifier) - \(String(describing: peripheral.name))")
        print("Adv data: \(advertisementData)")
        let advertisedName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
        /*
         TODO: review this, seems use CBAdvertisementDataLocalNameKey will not work / is not required
         But it can be that we receive the didDiscover message twice, once without the name, then afterwards with the name -> we should update our list if that's the case
         
         Discovered 5A7F01CA-CD35-37C4-38DA-0B6464CD94FA - nil
         Adv data: ["kCBAdvDataServiceUUIDs": <__NSArrayM 0x301c2c390>(
         Device Information,
         19B10000-E8F2-537E-4F6C-D104768A1214
         )
         , "kCBAdvDataRxSecondaryPHY": 0, "kCBAdvDataRxPrimaryPHY": 129, "kCBAdvDataIsConnectable": 1, "kCBAdvDataTimestamp": 742038261.889917]
         Discovered 5A7F01CA-CD35-37C4-38DA-0B6464CD94FA - Optional("Friend")
         Adv data: ["kCBAdvDataIsConnectable": 1, "kCBAdvDataLocalName": Friend, "kCBAdvDataRxPrimaryPHY": 129, "kCBAdvDataTimestamp": 742038261.891065, "kCBAdvDataServiceUUIDs": <__NSArrayM 0x301c2a580>(
         Device Information,
         19B10000-E8F2-537E-4F6C-D104768A1214
         )
         , "kCBAdvDataRxSecondaryPHY": 0]
         */
        
        if let servicesId = advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [Any] {
            for serviceId in servicesId {
                if let serviceId = serviceId as? CBUUID {
                    if let d = deviceRegistry.deviceTypeForService(uuid: serviceId) {
                        if discoveredPeripheralsMap[peripheral.identifier] == nil {
                            discoveredPeripheralsMap[peripheral.identifier] = peripheral
                            discoveredDevicesMap[peripheral.identifier] = DiscoveredDevice(name: peripheral.name ?? advertisedName ?? peripheral.identifier.uuidString,
                                                                                           deviceIdentifier: peripheral.identifier,
                                                                                           deviceType: .wearable(d.deviceConfiguration.reference))
                        }
                    }
                }
            }
        }
    }
    
}
