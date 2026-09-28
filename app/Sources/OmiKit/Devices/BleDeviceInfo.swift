import Foundation

// Device identity display model, ported from the v5 behavior spec
// (`react-native/src/app/DeviceSession.tsx` information rows +
// `docs/auth-and-sessions.md` "Device identity"):
//
//   Apple and Android read the available model, firmware, hardware,
//   manufacturer, and serial characteristics from the standard Device
//   Information service; connected-device details show Unknown for absent
//   or invalid values.
//
// Absent or invalid characteristic values parse to `nil` here; the display
// layer maps `nil` to "Unknown" via `displayValue(for:)` (same contract as
// `connected.information?.[field] ?? 'Unknown'` in the React Native tree).
// There is never an invented default firmware or identity.

public enum DeviceInfoField: String, Sendable, Hashable, CaseIterable {
    case model
    case firmware
    case hardware
    case manufacturer
    case serial

    /// UI label, matching the DeviceSession information rows.
    public var label: String {
        switch self {
        case .model: return "Model"
        case .firmware: return "Firmware"
        case .hardware: return "Hardware"
        case .manufacturer: return "Manufacturer"
        case .serial: return "Serial number"
        }
    }

    /// Standard Device Information service characteristic (Bluetooth SIG
    /// assigned numbers), as CoreBluetooth-style short UUIDs.
    public var characteristicUuid: String {
        switch self {
        case .model: return "2A24"
        case .serial: return "2A25"
        case .firmware: return "2A26"
        case .hardware: return "2A27"
        case .manufacturer: return "2A29"
        }
    }
}

public struct BleDeviceInfo: Sendable, Hashable {
    public var model: String?
    public var firmware: String?
    public var hardware: String?
    public var manufacturer: String?
    public var serial: String?

    public init(
        model: String? = nil, firmware: String? = nil, hardware: String? = nil,
        manufacturer: String? = nil, serial: String? = nil
    ) {
        self.model = model
        self.firmware = firmware
        self.hardware = hardware
        self.manufacturer = manufacturer
        self.serial = serial
    }

    public func value(for field: DeviceInfoField) -> String? {
        switch field {
        case .model: return model
        case .firmware: return firmware
        case .hardware: return hardware
        case .manufacturer: return manufacturer
        case .serial: return serial
        }
    }

    /// Display string: "Unknown" for absent or invalid values, per the spec.
    public func displayValue(for field: DeviceInfoField) -> String {
        value(for: field) ?? "Unknown"
    }
}

/// Pure parsers for Device Information characteristic values. Byte-level
/// and Skip-safe (no Character/UnicodeScalar classification); these run
/// identically on Apple, Android (transpiled), and in host tests.
public enum BleDeviceInfoParsing {
    /// Parses a Device Information characteristic read into a display
    /// value, or nil when the value is absent or invalid. Invalid means:
    /// empty after trimming ASCII whitespace, containing control bytes, or
    /// not valid UTF-8.
    public static func characteristicText(_ bytes: [UInt8]?) -> String? {
        guard var bytes else { return nil }
        // Trim ASCII whitespace from both ends (byte-level).
        while let first = bytes.first, isAsciiWhitespace(first) {
            bytes.removeFirst()
        }
        while let last = bytes.last, isAsciiWhitespace(last) {
            bytes.removeLast()
        }
        guard !bytes.isEmpty else { return nil }
        // Control bytes (including NUL padding) make the value invalid —
        // firmware bugs otherwise leak as garbage identity rows.
        for byte in bytes where byte < 0x20 || byte == 0x7F {
            return nil
        }
        // UTF-8 round-trip: decoding invalid sequences yields replacement
        // characters whose re-encoding differs from the source bytes.
        let text = String(decoding: bytes, as: UTF8.self)
        guard Array(text.utf8) == bytes else { return nil }
        return text
    }

    /// Parses one field from its characteristic bytes.
    public static func field(
        _ field: DeviceInfoField, bytes: [UInt8]?
    ) -> String? {
        characteristicText(bytes)
    }

    /// Parses a full Device Information snapshot from per-field reads; a
    /// failed/absent read simply leaves that field nil (Unknown).
    public static func deviceInfo(
        reads: [DeviceInfoField: [UInt8]?]
    ) -> BleDeviceInfo {
        var info = BleDeviceInfo()
        for (field, bytes) in reads {
            let value = characteristicText(bytes)
            switch field {
            case .model: info.model = value
            case .firmware: info.firmware = value
            case .hardware: info.hardware = value
            case .manufacturer: info.manufacturer = value
            case .serial: info.serial = value
            }
        }
        return info
    }

    private static func isAsciiWhitespace(_ byte: UInt8) -> Bool {
        byte == 0x20 || byte == 0x09 || byte == 0x0A || byte == 0x0D
    }
}
