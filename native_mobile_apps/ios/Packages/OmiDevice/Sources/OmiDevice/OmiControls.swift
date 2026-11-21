@preconcurrency import CoreBluetooth
import Foundation

/// The Omi's settings, feature flags, haptic motor and serial number. Firmware
/// `lib/core/transport.c` (settings + features services), `haptic.c`, `lib/core/features.h`;
/// Flutter `connectors/omi_connection.dart:1186-1290`, `device_connection.dart:404-430`.
public extension OmiGATT {
    static let settingsService = CBUUID(string: "19b10010-e8f2-537e-4f6c-d104768a1214")
    /// LED brightness, one byte 0…100 (read/write).
    static let ledDimRatio = CBUUID(string: "19b10011-e8f2-537e-4f6c-d104768a1214")
    /// Microphone gain level, one byte 0 (mute) … 8 (+40 dB) (read/write).
    static let micGain = CBUUID(string: "19b10012-e8f2-537e-4f6c-d104768a1214")
    /// One byte, 1 while on the charger (read/notify).
    static let chargingStatus = CBUUID(string: "19b10013-e8f2-537e-4f6c-d104768a1214")
    static let featuresService = CBUUID(string: "19b10020-e8f2-537e-4f6c-d104768a1214")
    /// `uint32` little-endian bitmask of `Features` (read).
    static let features = CBUUID(string: "19b10021-e8f2-537e-4f6c-d104768a1214")
    /// The haptic service shares its UUID with the (empty) speaker service in firmware.
    static let hapticService = CBUUID(string: "cab1ab95-2ea5-4f4d-bb56-874b72cfc984")
    static let haptic = CBUUID(string: "cab1ab96-2ea5-4f4d-bb56-874b72cfc984")
    static let serialNumber = CBUUID(string: "2A25")

    /// What this firmware supports (`omi_feature_t`). Old firmware without the features service
    /// reports nothing, so its controls stay hidden.
    struct Features: OptionSet, Sendable, Hashable {
        public let rawValue: UInt32
        public init(rawValue: UInt32) {
            self.rawValue = rawValue
        }

        public static let speaker = Features(rawValue: 1 << 0)
        public static let accelerometer = Features(rawValue: 1 << 1)
        public static let button = Features(rawValue: 1 << 2)
        public static let battery = Features(rawValue: 1 << 3)
        public static let usb = Features(rawValue: 1 << 4)
        public static let haptic = Features(rawValue: 1 << 5)
        public static let offlineStorage = Features(rawValue: 1 << 6)
        public static let ledDimming = Features(rawValue: 1 << 7)
        public static let micGain = Features(rawValue: 1 << 8)

        /// A read shorter than four bytes is an empty set (Flutter returns 0).
        public init(_ value: Data) {
            guard value.count >= 4 else {
                self.init(rawValue: 0)
                return
            }
            let raw = value.prefix(4).reversed().reduce(UInt32(0)) { $0 << 8 | UInt32($1) }
            self.init(rawValue: raw)
        }
    }

    /// A haptic pulse; the firmware maps 1/2/3 to 100/300/500 ms.
    enum Haptic: UInt8, Sendable {
        case short = 1
        case medium = 2
        case long = 3

        public var payload: Data {
            Data([rawValue])
        }
    }

    /// The writable controls, for `DeviceDriving.write(_:_:)`.
    enum Control: Sendable, Equatable {
        case ledBrightness
        case micGain
        case haptic

        public var characteristic: CBUUID {
            switch self {
            case .ledBrightness: OmiGATT.ledDimRatio
            case .micGain: OmiGATT.micGain
            case .haptic: OmiGATT.haptic
            }
        }
    }

    /// Mic gain levels the firmware accepts (higher values are capped at 8).
    static let micGainLevels = 0 ... 8

    static func ledBrightnessPayload(_ percent: Int) -> Data {
        Data([UInt8(min(100, max(0, percent)))])
    }

    static func micGainPayload(_ level: Int) -> Data {
        Data([UInt8(min(micGainLevels.upperBound, max(micGainLevels.lowerBound, level)))])
    }

    /// One-byte settings reads (brightness, gain); `nil` for an empty read.
    static func settingValue(_ value: Data) -> Int? {
        value.first.map(Int.init)
    }

    static func isCharging(_ value: Data) -> Bool? {
        value.first.map { $0 == 1 }
    }

    /// The DIS serial when it is a real per-unit id: CV1 publishes its nRF FICR id as exactly 16
    /// hex characters; constants ("unknown") and an unset FICR (one repeated digit) are dropped.
    static func serialNumber(_ value: Data) -> String? {
        guard let text = String(data: value, encoding: .utf8) else { return nil }
        let serial = text.replacingOccurrences(of: "\u{0}", with: "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard serial.count == 16, serial.allSatisfy(\.isHexDigit), Set(serial).count > 1 else { return nil }
        return serial
    }

    /// Find my Omi: three long pulses, 750 ms apart (`device_connection.dart:409`).
    static let findPattern: [Haptic] = [.long, .long, .long]
    static let findPulseGap: Duration = .milliseconds(750)
}
