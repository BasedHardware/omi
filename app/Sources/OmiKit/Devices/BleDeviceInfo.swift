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

/// Pure parser delegating to the shared C++ middleware (`omi_device`
/// characteristic validation: ASCII-whitespace trim, control-byte and UTF-8
/// rejection). Absent or invalid reads parse to `nil`; the display layer
/// maps `nil` to "Unknown" (same contract as
/// `connected.information?.[field] ?? 'Unknown'` in the React Native tree).
/// These run identically on Apple, Android (via the JNI bridge), and in host
/// tests.
public enum BleDeviceInfoParsing {
    /// Parses a Device Information characteristic read into a display
    /// value, or nil when the value is absent or invalid. Invalid means:
    /// empty after trimming ASCII whitespace, containing control bytes, or
    /// not valid UTF-8.
    public static func characteristicText(_ bytes: [UInt8]?) -> String? {
        Policy.deviceCharacteristicText(bytes)
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
}
