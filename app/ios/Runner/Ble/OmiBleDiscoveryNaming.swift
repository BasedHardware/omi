import CoreBluetooth
import Foundation

/// Pure helpers for naming a peripheral from its scan data (testable without a
/// live radio), mirroring `OmiBlePairingPolicy`.
///
/// `CBPeripheral.name` is often empty until the phone has connected once, while
/// NotePin S puts "NotePin" only in the advertisement (#18705, #20033).
enum OmiBleDiscoveryNaming {
    /// Fallback name when a NotePin advertisement carries no local name.
    /// `NativeBluetoothDiscoverer` classifies PLAUD via `name.contains("notepin")`,
    /// so this makes the device surface and route to `DeviceType.plaud`.
    static let notePinFallbackName = "NotePin"

    /// PLAUD manufacturer id 93 (0x5D), little-endian in the advertisement,
    /// matching macOS discovery in `desktop/macos/.../BtDevice.swift`.
    private static let plaudManufacturerId: UInt16 = 93
    private static let notePinPayload: [UInt8] = [0x04, 0x56, 0xCF, 0x00]

    private static let plaudServiceUuid16 = CBUUID(string: "1910")
    private static let plaudServiceUuid128 = CBUUID(string: "00001910-0000-1000-8000-00805F9B34FB")

    /// Resolve the scan-time name, preferring what the advertisement itself
    /// carries over `CBPeripheral`'s cached name, then the NotePin fallback.
    static func discoveredName(
        advertisedLocalName: String?,
        cachedName: String?,
        advertisementData: [String: Any]
    ) -> String {
        if let advertised = normalized(advertisedLocalName) {
            return advertised
        }
        if let cached = normalized(cachedName) {
            return cached
        }
        if isNotePinAdvertisement(advertisementData) {
            return notePinFallbackName
        }
        return ""
    }

    /// PLAUD manufacturer id with the NotePin payload or PLAUD service UUID (1910).
    static func isNotePinAdvertisement(_ advertisementData: [String: Any]) -> Bool {
        if let serviceUUIDs = advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] {
            if serviceUUIDs.contains(plaudServiceUuid16) || serviceUUIDs.contains(plaudServiceUuid128) {
                return true
            }
        }
        guard let manufacturerData = advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data,
              manufacturerData.count >= 2 + notePinPayload.count
        else {
            return false
        }
        let manufacturerId = UInt16(manufacturerData[0]) | (UInt16(manufacturerData[1]) << 8)
        guard manufacturerId == plaudManufacturerId else { return false }
        return Array(manufacturerData[2..<(2 + notePinPayload.count)]) == notePinPayload
    }

    private static func normalized(_ name: String?) -> String? {
        guard let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty
        else {
            return nil
        }
        return trimmed
    }
}
