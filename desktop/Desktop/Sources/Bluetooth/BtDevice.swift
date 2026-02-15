import CoreBluetooth
import Foundation

/// Represents a discovered or connected Bluetooth device
/// Ported from: omi/app/lib/backend/schema/bt_device/bt_device.dart
struct BtDevice: Identifiable, Codable, Equatable {
    let id: String
    var name: String
    var type: DeviceType
    var rssi: Int

    // Device info (populated after connection)
    var modelNumber: String?
    var firmwareRevision: String?
    var hardwareRevision: String?
    var manufacturerName: String?

    // MARK: - Initialization

    init(
        id: String,
        name: String,
        type: DeviceType,
        rssi: Int,
        modelNumber: String? = nil,
        firmwareRevision: String? = nil,
        hardwareRevision: String? = nil,
        manufacturerName: String? = nil
    ) {
        self.id = id
        self.name = name
        self.type = type
        self.rssi = rssi
        self.modelNumber = modelNumber
        self.firmwareRevision = firmwareRevision
        self.hardwareRevision = hardwareRevision
        self.manufacturerName = manufacturerName
    }

    // MARK: - Computed Properties

    /// Short device ID for display (last 6 characters)
    var shortId: String {
        if id == "apple-watch" {
            return "watchOS"
        }
        let cleaned = id.replacingOccurrences(of: ":", with: "")
        let components = cleaned.split(separator: "-")
        if let last = components.last, last.count >= 6 {
            return String(last.suffix(6))
        }
        return String(id.prefix(6))
    }

    /// Display name with fallback
    var displayName: String {
        name.isEmpty ? type.displayName : name
    }

    /// Model number with fallback to device type name
    var displayModelNumber: String {
        modelNumber ?? type.displayName
    }

    /// Firmware revision with fallback
    var displayFirmwareRevision: String {
        firmwareRevision ?? type.defaultFirmwareRevision
    }

    /// Hardware revision with fallback
    var displayHardwareRevision: String {
        hardwareRevision ?? type.defaultHardwareRevision
    }

    /// Manufacturer name with fallback
    var displayManufacturerName: String {
        manufacturerName ?? type.manufacturerName
    }

    // MARK: - Equatable

    static func == (lhs: BtDevice, rhs: BtDevice) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Device Detection

extension BtDevice {

    /// Check if a discovered peripheral is a supported device
    /// - Parameters:
    ///   - peripheral: The CoreBluetooth peripheral
    ///   - advertisementData: Advertisement data from discovery
    /// - Returns: true if the device is supported
    static func isSupportedDevice(
        peripheral: CBPeripheral,
        advertisementData: [String: Any]
    ) -> Bool {
        return detectDeviceType(peripheral: peripheral, advertisementData: advertisementData) != nil
    }

    /// Detect the device type from a discovered peripheral
    /// - Parameters:
    ///   - peripheral: The CoreBluetooth peripheral
    ///   - advertisementData: Advertisement data from discovery
    /// - Returns: The detected device type, or nil if not supported
    static func detectDeviceType(
        peripheral: CBPeripheral,
        advertisementData: [String: Any]
    ) -> DeviceType? {
        let name = peripheral.name?.lowercased() ?? ""
        let serviceUUIDs = advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []

        // Check Bee (by name or service UUID)
        if name.contains("bee") || serviceUUIDs.contains(DeviceUUIDs.Bee.service) {
            return .bee
        }

        // Check PLAUD (by manufacturer data or name)
        if isPlaudDevice(advertisementData: advertisementData) || name.hasPrefix("plaud") {
            return .plaud
        }

        // Check Fieldy/Compass
        if name == "compass" || name == "fieldy" || serviceUUIDs.contains(DeviceUUIDs.Fieldy.service) {
            return .fieldy
        }

        // Check Friend Pendant
        if name.hasPrefix("friend_") || serviceUUIDs.contains(DeviceUUIDs.FriendPendant.service) {
            return .friendPendant
        }

        // Check Limitless
        if name.contains("limitless") || name.contains("pendant") || serviceUUIDs.contains(DeviceUUIDs.Limitless.service) {
            return .limitless
        }

        // Check Omi (main service UUID)
        if serviceUUIDs.contains(DeviceUUIDs.Omi.mainService) {
            // Note: OpenGlass detection requires service discovery after connection
            // to check for image streaming characteristic
            return .omi
        }

        // Check Frame
        if serviceUUIDs.contains(DeviceUUIDs.Frame.service) {
            return .frame
        }

        return nil
    }

    /// Check if this is a PLAUD device from advertisement data
    private static func isPlaudDevice(advertisementData: [String: Any]) -> Bool {
        guard let manufacturerData = advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data else {
            return false
        }

        // PLAUD uses manufacturer ID 93 (0x5D)
        // Manufacturer data format: [LSB of ID, MSB of ID, ...payload...]
        guard manufacturerData.count >= 2 else { return false }

        let manufacturerId = UInt16(manufacturerData[0]) | (UInt16(manufacturerData[1]) << 8)
        if manufacturerId == DeviceUUIDs.PLAUD.manufacturerId {
            // Known NotePin pattern: 0456cf00
            if manufacturerData.count >= 6 {
                let payload = manufacturerData.dropFirst(2)
                if payload.count >= 4 &&
                    payload[payload.startIndex] == 0x04 &&
                    payload[payload.startIndex + 1] == 0x56 &&
                    payload[payload.startIndex + 2] == 0xcf &&
                    payload[payload.startIndex + 3] == 0x00 {
                    return true
                }
            }
            // Accept any device with manufacturer ID 93 with data
            return manufacturerData.count > 2
        }

        return false
    }

    /// Create a BtDevice from a CoreBluetooth discovery result
    static func from(
        peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi: NSNumber
    ) -> BtDevice? {
        guard let deviceType = detectDeviceType(
            peripheral: peripheral,
            advertisementData: advertisementData
        ) else {
            return nil
        }

        return BtDevice(
            id: peripheral.identifier.uuidString,
            name: peripheral.name ?? deviceType.displayName,
            type: deviceType,
            rssi: rssi.intValue
        )
    }

    /// Update device type to OpenGlass if image streaming is available
    /// Call this after service discovery to detect OpenGlass devices
    func checkingForOpenGlass(services: [CBService]) -> BtDevice {
        guard type == .omi else { return self }

        // Check if the Omi service has the image data stream characteristic
        for service in services where service.uuid == DeviceUUIDs.Omi.mainService {
            let hasImageStream = service.characteristics?.contains { char in
                char.uuid == DeviceUUIDs.Omi.imageDataStream
            } ?? false

            if hasImageStream {
                var updated = self
                updated.type = .openglass
                return updated
            }
        }

        return self
    }
}

// MARK: - Device Info Retrieval

extension BtDevice {

    /// Update device with info read from standard Device Information Service
    func withDeviceInfo(
        modelNumber: String?,
        firmwareRevision: String?,
        hardwareRevision: String?,
        manufacturerName: String?
    ) -> BtDevice {
        var updated = self
        updated.modelNumber = modelNumber ?? self.modelNumber
        updated.firmwareRevision = firmwareRevision ?? self.firmwareRevision
        updated.hardwareRevision = hardwareRevision ?? self.hardwareRevision
        updated.manufacturerName = manufacturerName ?? self.manufacturerName
        return updated
    }
}

// MARK: - Persistence

extension BtDevice {

    /// UserDefaults key for storing paired device
    private static let pairedDeviceKey = "pairedBtDevice"

    /// Save this device as the paired device
    func saveAsPairedDevice() {
        if let encoded = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(encoded, forKey: Self.pairedDeviceKey)
        }
    }

    /// Load the previously paired device
    static func loadPairedDevice() -> BtDevice? {
        guard let data = UserDefaults.standard.data(forKey: pairedDeviceKey),
              let device = try? JSONDecoder().decode(BtDevice.self, from: data) else {
            return nil
        }
        return device
    }

    /// Clear the paired device
    static func clearPairedDevice() {
        UserDefaults.standard.removeObject(forKey: pairedDeviceKey)
    }
}
