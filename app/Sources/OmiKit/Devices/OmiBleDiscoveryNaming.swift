import Foundation

// Pure discovery-naming helpers, adapted from the upstream maintained
// implementation at `app/ios/Runner/Ble/OmiBleDiscoveryNaming.swift`
// (branch omi/main). The upstream file is CoreBluetooth-typed; this port is
// byte-level and platform-neutral so it can be unit tested and transpiled
// to Kotlin. Semantics preserved:
//
// `CBPeripheral.name` is often empty until the phone has connected once,
// while NotePin S puts "NotePin" only in the advertisement (#18705).

/// Fallback name when a NotePin advertisement carries no local name.
/// The upstream discoverer classifies PLAUD via `name.contains("notepin")`,
/// so this makes the device surface and route as a NotePin.
public let omiNotePinFallbackName = "NotePin"

public enum OmiBleDiscoveryNaming {
    /// PLAUD manufacturer id 93 (0x5D), little-endian in the advertisement,
    /// matching macOS discovery in `desktop/macos/.../BtDevice.swift`.
    private static let plaudManufacturerId = UInt16(93)
    private static let notePinPayload: [UInt8] = [0x04, 0x56, 0xCF, 0x00]

    /// Resolve the scan-time name, preferring what the advertisement itself
    /// carries over the platform's cached name, then the NotePin fallback.
    /// `manufacturerData` is the raw advertisement manufacturer-specific
    /// data (id bytes included), or nil when the platform omitted it.
    public static func discoveredName(
        advertisedLocalName: String?,
        cachedName: String?,
        manufacturerData: [UInt8]?
    ) -> String {
        if let advertised = normalized(advertisedLocalName) {
            return advertised
        }
        if let cached = normalized(cachedName) {
            return cached
        }
        if isNotePinAdvertisement(manufacturerData) {
            return omiNotePinFallbackName
        }
        return ""
    }

    /// PLAUD manufacturer id with the NotePin payload.
    public static func isNotePinAdvertisement(
        _ manufacturerData: [UInt8]?
    ) -> Bool {
        guard let manufacturerData,
            manufacturerData.count >= 2 + notePinPayload.count
        else {
            return false
        }
        let manufacturerId =
            UInt16(manufacturerData[0]) | (UInt16(manufacturerData[1]) << 8)
        guard manufacturerId == plaudManufacturerId else { return false }
        return Array(
            manufacturerData[2..<(2 + notePinPayload.count)]
        ) == notePinPayload
    }

    private static func normalized(_ name: String?) -> String? {
        guard let name else { return nil }
        var bytes = Array(name.utf8)
        while let first = bytes.first, first == 0x20 || first == 0x0A
            || first == 0x0D || first == 0x09
        {
            bytes.removeFirst()
        }
        while let last = bytes.last, last == 0x20 || last == 0x0A
            || last == 0x0D || last == 0x09
        {
            bytes.removeLast()
        }
        guard !bytes.isEmpty else { return nil }
        return String(decoding: bytes, as: UTF8.self)
    }
}
