import Foundation
import AccessorySetupKit
import UIKit
import CoreBluetooth

@available(iOS 18.0, *)
class AccessorySetupManager: NSObject {
    private var session: ASAccessorySession?
    private var eventHandler: ((String, [String: Any]) -> Void)?
    
    override init() {
        super.init()
        setupSession()
    }
    
    private func setupSession() {
        session = ASAccessorySession()
        session?.activate(on: DispatchQueue.main) { [weak self] event in
            self?.handleSessionEvent(event: event)
        }
    }
    
    private func handleSessionEvent(event: ASAccessoryEvent) {
        var eventData: [String: Any] = [:]
        
        switch event.eventType {
        case .activated:
            eventHandler?("sessionActivated", [:])
            
        case .accessoryAdded:
            if let accessory = event.accessory {
                eventData = [
                    "accessoryId": accessory.bluetoothIdentifier?.uuidString ?? "",
                    "displayName": accessory.displayName,
                    "isConnected": true
                ]
            }
            eventHandler?("accessoryAdded", eventData)
            
        case .accessoryChanged:
            if let accessory = event.accessory {
                eventData = [
                    "accessoryId": accessory.bluetoothIdentifier?.uuidString ?? "",
                    "displayName": accessory.displayName
                ]
            }
            eventHandler?("accessoryChanged", eventData)
            
        case .accessoryRemoved:
            if let accessory = event.accessory {
                eventData = [
                    "accessoryId": accessory.bluetoothIdentifier?.uuidString ?? ""
                ]
            }
            eventHandler?("accessoryRemoved", eventData)
            
        case .pickerDidPresent:
            eventHandler?("pickerDidPresent", [:])
            
        case .pickerDidDismiss:
            eventHandler?("pickerDidDismiss", [:])
            
        default:
            eventHandler?("unknownEvent", ["eventType": event.eventType.rawValue])
        }
    }
    
    func setEventHandler(_ handler: @escaping (String, [String: Any]) -> Void) {
        self.eventHandler = handler
    }
    
    func showAccessoryPicker(completion: @escaping (Bool, String?) -> Void) {
        guard let session = session else {
            completion(false, "Session not initialized")
            return
        }
        
        // Create display items for Omi devices
        let omiDisplayItems = createOmiDisplayItems()
        
        session.showPicker(for: omiDisplayItems) { error in
            DispatchQueue.main.async {
                if let error = error {
                    completion(false, error.localizedDescription)
                } else {
                    completion(true, nil)
                }
            }
        }
    }
    
    private func createOmiDisplayItems() -> [ASPickerDisplayItem] {
        var displayItems: [ASPickerDisplayItem] = []
        
        // Omi DevKit - specific for DevKit devices (check this first)
        let devkitDescriptor = ASDiscoveryDescriptor()
        devkitDescriptor.bluetoothServiceUUID = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
        devkitDescriptor.bluetoothNameSubstring = "DevK"  // Matches both "DevKit" and "DevK"
        
        if let devkitImage = UIImage(named: "omi-devkit-without-rope") {
            let devkitDisplayItem = ASPickerDisplayItem(
                name: "Omi DevKit",
                productImage: devkitImage,
                descriptor: devkitDescriptor
            )
            displayItems.append(devkitDisplayItem)
        }
        
        // Regular Omi Device - fallback for devices that don't match DevKit pattern
        let omiDescriptor = ASDiscoveryDescriptor()
        omiDescriptor.bluetoothServiceUUID = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
        // No name substring - this will match any device with the service UUID that doesn't match more specific descriptors
        
        if let omiImage = UIImage(named: "omi-without-rope") {
            let omiDisplayItem = ASPickerDisplayItem(
                name: "Omi",
                productImage: omiImage,
                descriptor: omiDescriptor
            )
            displayItems.append(omiDisplayItem)
        }
        
        // Omi Glass/Frame - match any device containing "Glass"
        let frameDescriptor = ASDiscoveryDescriptor()
        frameDescriptor.bluetoothServiceUUID = CBUUID(string: "7A230001-5475-A6A4-654C-8431F6AD49C4")
        frameDescriptor.bluetoothNameSubstring = "Glass"  // Matches "Omi Glass", "OMI Glass", etc.
        
        if let frameImage = UIImage(named: "omi-glass") {
            let frameDisplayItem = ASPickerDisplayItem(
                name: "Omi Glass",
                productImage: frameImage,
                descriptor: frameDescriptor
            )
            displayItems.append(frameDisplayItem)
        }
        
        return displayItems
    }
    
    func getConnectedAccessories() -> [[String: Any]] {
        guard let session = session else { return [] }
        
        return session.accessories.map { accessory in
            return [
                "accessoryId": accessory.bluetoothIdentifier?.uuidString ?? "",
                "displayName": accessory.displayName,
                "bluetoothIdentifier": accessory.bluetoothIdentifier?.uuidString ?? ""
            ]
        }
    }
    
    func removeAccessory(withId accessoryId: String, completion: @escaping (Bool, String?) -> Void) {
        guard let session = session else {
            completion(false, "Session not initialized")
            return
        }
        
        let accessory = session.accessories.first { accessory in
            accessory.bluetoothIdentifier?.uuidString == accessoryId
        }
        
        guard let accessory = accessory else {
            completion(false, "Accessory not found")
            return
        }
        
        session.removeAccessory(accessory) { error in
            DispatchQueue.main.async {
                if let error = error {
                    completion(false, error.localizedDescription)
                } else {
                    completion(true, nil)
                }
            }
        }
    }
} 