import Foundation
import CoreBluetooth
import React

@objc(OmiModule)
class OmiModule: RCTEventEmitter {
    
    private var centralManager: CBCentralManager!
    private var peripherals: [String: CBPeripheral] = [:]
    private var characteristics: [String: [CBUUID: CBCharacteristic]] = [:]
    private var audioNotifying: [String: Bool] = [:]
    private var hasListeners: Bool = false
    
    // Service and characteristic UUIDs
    private let omiServiceUUID = CBUUID(string: "19b10000-e8f2-537e-4f6c-d104768a1214")
    private let audioDataStreamCharacteristicUUID = CBUUID(string: "19b10001-e8f2-537e-4f6c-d104768a1214")
    private let audioCodecCharacteristicUUID = CBUUID(string: "19b10002-e8f2-537e-4f6c-d104768a1214")
    private let buttonServiceUUID = CBUUID(string: "23ba7924-0000-1000-7450-346eac492e92")
    private let buttonTriggerCharacteristicUUID = CBUUID(string: "23ba7925-0000-1000-7450-346eac492e92")
    private let batteryServiceUUID = CBUUID(string: "0000180f-0000-1000-8000-00805f9b34fb")
    private let batteryLevelCharacteristicUUID = CBUUID(string: "00002a19-0000-1000-8000-00805f9b34fb")
    
    @objc override init() {
        super.init()
        centralManager = CBCentralManager(delegate: self, queue: nil)
    }
    
    // Required for RCTEventEmitter
    @objc override func supportedEvents() -> [String] {
        return [
            "connectionStateChanged",
            "audioBytesReceived",
            "deviceDiscovered"
        ]
    }
    
    // Called when this module's first listener is added
    @objc override func startObserving() {
        hasListeners = true
    }
    
    // Called when this module's last listener is removed
    @objc override func stopObserving() {
        hasListeners = false
    }
    
    @objc(connect:withResolver:withRejecter:)
    func connect(deviceId: String, resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(nil)
        
        // Example of sending an event
        if hasListeners {
            sendEvent(withName: "connectionStateChanged", body: [
                "id": deviceId,
                "state": "connected"
            ])
        }
    }
    
    @objc(disconnect:withResolver:withRejecter:)
    func disconnect(deviceId: String, resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(nil)
        
        // Example of sending an event
        if hasListeners {
            sendEvent(withName: "connectionStateChanged", body: [
                "id": deviceId,
                "state": "disconnected"
            ])
        }
    }
    
    @objc(isConnected:withResolver:withRejecter:)
    func isConnected(deviceId: String, resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(false)
    }
    
    @objc(getAudioCodec:withResolver:withRejecter:)
    func getAudioCodec(deviceId: String, resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now - return PCM8 (1)
        resolve(1)
    }
    
    @objc(startAudioBytesNotifications:withResolver:withRejecter:)
    func startAudioBytesNotifications(deviceId: String, resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(nil)
        
        // Example of how to send audio bytes event
        if hasListeners {
            // Mock audio data
            let mockAudioBytes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            sendEvent(withName: "audioBytesReceived", body: [
                "id": deviceId,
                "bytes": mockAudioBytes
            ])
        }
    }
    
    @objc(stopAudioBytesNotifications:withResolver:withRejecter:)
    func stopAudioBytesNotifications(deviceId: String, resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(nil)
    }
    
    @objc(startScan:withRejecter:)
    func startScan(resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(nil)
    }
    
    @objc(stopScan:withRejecter:)
    func stopScan(resolve: @escaping RCTPromiseResolveBlock, reject: @escaping RCTPromiseRejectBlock) {
        // Mock implementation for now
        resolve(nil)
    }
}

extension OmiModule: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        // Handle state changes
    }
}

extension OmiModule: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        // Handle service discovery
    }
    
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        // Handle characteristic discovery
    }
    
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        // Handle characteristic value updates
    }
}
