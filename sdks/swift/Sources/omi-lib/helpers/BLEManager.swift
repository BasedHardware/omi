//
//  BLEManager.swift
//  PALApp
//
//  Created by Eric Bariaux on 27/04/2024.
//

import Foundation
import CoreBluetooth
import Combine
import os

enum BLEStatus {
    case off
    case on
    case scanning
    case connecting
    case connected
    case linked
    case disconnected
}

protocol BLEManagerDelegate: AnyObject {
    func lostConnection()
}

class BLEManager : NSObject, ObservableObject {
    
    weak var delegate: BLEManagerDelegate?
    let log = Logger(subsystem: "be.nelcea.PALApp", category: "BLE")

    init(deviceRegistry: WearableDeviceRegistry) {
        self.deviceRegistry = deviceRegistry
    }
    
    @Published var status: BLEStatus = .off
    
    var servicesRegistry: [CBUUID: CBService] = [:]
    var characteristicsRegistry: [CBUUID: CBCharacteristic] = [:]

    let valueChanges = PassthroughSubject<(CBUUID, Data), Error>()
    
    var connectedDevice: WearableDevice?
    
    private var deviceRegistry: WearableDeviceRegistry

    private var manager: CBCentralManager?
    private var peripheral: CBPeripheral?
    
    private var uuidToConnect: UUID?
    private var peripheralToConnect: CBPeripheral?

    func reconnect(to: UUID) {
        if manager == nil {
            manager = CBCentralManager(delegate: self, queue: nil)
        }
        uuidToConnect = to
        if let manager, manager.state == .poweredOn {
            forceConnect()
        }
    }
    
    func stopConnecting() {
        if let manager, let peripheralToConnect {
            manager.cancelPeripheralConnection(peripheralToConnect)
        }
    }
    
    func disconnect() {
        if let manager, let peripheral {
            manager.cancelPeripheralConnection(peripheral)
        }
    }
    
    func setNotify(enabled: Bool, forCharacteristics characteristicId: CBUUID) {
        if let peripheral, let characteritic = characteristicsRegistry[characteristicId] {
            peripheral.setNotifyValue(enabled, for: characteritic)
        }
    }
    
    /// Force connection to a peripheral irrelevant of the power state of the manager, will result in error if not powered on
    private func forceConnect() {
        if let manager, let uuid = uuidToConnect {
            if let p = manager.retrievePeripherals(withIdentifiers: [uuid]).first {
                peripheralToConnect = p
                status = .connecting
                manager.connect(p, options: [CBConnectPeripheralOptionNotifyOnDisconnectionKey: true])
                // connect do not timeout, need to explicitly cancel it
            }
            uuidToConnect = nil
        }
    }
}

extension BLEManager : CBCentralManagerDelegate {

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        status = (central.state == .poweredOn ? .on : .off)

        if central.state == .poweredOn && uuidToConnect != nil {
            forceConnect()
        }
    }
    
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        status = .connected
        self.peripheral = peripheral
        log.info("Did connect to peripheral with identifier: \(peripheral.identifier)")
        peripheral.delegate = self
        peripheral.discoverServices(nil)
    }
    
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, timestamp: CFAbsoluteTime, isReconnecting: Bool, error: (any Error)?) {
        log.info("Did disconnect \(peripheral), isReconnecting \(isReconnecting)")
        if let error {
            log.info("\(error.localizedDescription)")
        }
        connectedDevice = nil
        characteristicsRegistry.removeAll()
        servicesRegistry.removeAll()
        self.peripheral = nil
        status = .disconnected
        
        self.delegate?.lostConnection()
        /*
         Did disconnect <CBPeripheral: 0x301d20410, identifier = CDB4FE3D-F827-2E5E-BCE0-39FAA839BD8E, name = Friend, mtu = 23, state = disconnected>
         The connection has timed out unexpectedly.
         */
    }

}

extension BLEManager : CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: (any Error)?) {
        if let services = peripheral.services {
            for service in services {
                if let wearable = deviceRegistry.deviceTypeForService(uuid: service.uuid) {
                    connectedDevice = wearable.init(bleManager: self, name: peripheral.name ?? peripheral.identifier.uuidString)
                    status = .linked
                }
            }
            
            for service in services {
                log.debug("Discovered service \(service)")
                servicesRegistry[service.uuid] = service
                peripheral.discoverCharacteristics(nil, for: service)
            }
        }
    }
    
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: (any Error)?) {
        if let characteristics = service.characteristics {
            for c in characteristics {
                characteristicsRegistry[c.uuid] = c
                log.debug("Discovered characteristic \(c)")
                if let connectedDevice {
                    if type(of: connectedDevice).deviceConfiguration.notifyCharacteristicsUUIDs.contains(c.uuid) {
                        log.debug("Asking for notifications")
                        peripheral.setNotifyValue(true, for: c)
                        peripheral.readValue(for: c)
                    } else {
                        peripheral.readValue(for: c)
                    }
                }
            }
        }
    }
    
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: (any Error)?) {
        if let v = characteristic.value {
            valueChanges.send((characteristic.uuid, v))
        }
    }

}
