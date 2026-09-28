import Foundation

// Discovery naming delegates to the shared C++ middleware (`omi_device`):
// name trimming and preference order, the PLAUD/NotePin manufacturer-data
// match, and the omi-like discovery filter all live in C++ so every platform
// classifies identically. Retained semantics (from the upstream maintained
// `app/ios/Runner/Ble/OmiBleDiscoveryNaming.swift`, branch omi/main):
//
// `CBPeripheral.name` is often empty until the phone has connected once,
// while NotePin S puts "NotePin" only in the advertisement (#18705).

/// Fallback name when a NotePin advertisement carries no local name.
/// The upstream discoverer classifies PLAUD via `name.contains("notepin")`,
/// so this makes the device surface and route as a NotePin.
public let omiNotePinFallbackName = "NotePin"

public enum OmiBleDiscoveryNaming {
    /// Resolve the scan-time name, preferring what the advertisement itself
    /// carries over the platform's cached name, then the NotePin fallback.
    /// `manufacturerData` is the raw advertisement manufacturer-specific
    /// data (id bytes included), or nil when the platform omitted it.
    public static func discoveredName(
        advertisedLocalName: String?,
        cachedName: String?,
        manufacturerData: [UInt8]?
    ) -> String {
        Policy.deviceDiscoveredName(
            advertisedLocalName: advertisedLocalName, cachedName: cachedName,
            manufacturerData: manufacturerData)
    }

    /// PLAUD manufacturer id (0x5D little-endian) with the NotePin payload.
    public static func isNotePinAdvertisement(
        _ manufacturerData: [UInt8]?
    ) -> Bool {
        Policy.deviceIsNotePinAdvertisement(manufacturerData)
    }
}
