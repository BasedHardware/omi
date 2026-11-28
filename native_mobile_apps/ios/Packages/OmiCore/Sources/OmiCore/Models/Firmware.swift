import Foundation

/// An Omi firmware version, compared like the backend does (`backend/routers/firmware.py`
/// `_parse_firmware_version`): an optional `v`, dot-separated integers, padded to three parts.
public struct FirmwareVersion: Comparable, Hashable, Sendable, CustomStringConvertible {
    public let parts: [Int]

    /// `nil` for anything that is not plain numbers ("", "Unknown", "3.0.x"): an unknown
    /// version never counts as older than a release.
    public init?(_ string: String?) {
        guard var text = string?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), !text.isEmpty else { return nil }
        if text.hasPrefix("v") { text.removeFirst() }
        var parts: [Int] = []
        for piece in text.split(separator: ".", omittingEmptySubsequences: false) {
            guard let number = Int(piece), number >= 0 else { return nil }
            parts.append(number)
        }
        while parts.count < 3 {
            parts.append(0)
        }
        self.parts = parts
    }

    public static func < (lhs: Self, rhs: Self) -> Bool {
        let count = max(lhs.parts.count, rhs.parts.count)
        let left = lhs.parts + Array(repeating: 0, count: count - lhs.parts.count)
        let right = rhs.parts + Array(repeating: 0, count: count - rhs.parts.count)
        return left.lexicographicallyPrecedes(right)
    }

    public static func == (lhs: Self, rhs: Self) -> Bool {
        !(lhs < rhs) && !(rhs < lhs)
    }

    public func hash(into hasher: inout Hasher) {
        var trimmed = parts
        while trimmed.count > 3, trimmed.last == 0 {
            trimmed.removeLast()
        }
        hasher.combine(trimmed)
    }

    public var description: String {
        parts.map(String.init).joined(separator: ".")
    }
}

/// The newest firmware the backend offers for a device (`GET v2/firmware/latest`).
public struct FirmwareRelease: Codable, Hashable, Sendable {
    public let version: String
    /// The device must already run at least this version to take the update.
    public let minVersion: String?
    /// An MCUboot OTA package (zip with `manifest.json` + images) on GitHub releases.
    public let zipURL: URL
    /// `true`: the old Nordic Secure DFU bootloader (DevKit), which this app does not flash.
    public let isLegacySecureDFU: Bool
    /// One line of release notes, when the release has any.
    public let notes: String?

    public init(version: String, minVersion: String?, zipURL: URL, isLegacySecureDFU: Bool, notes: String?) {
        self.version = version
        self.minVersion = minVersion
        self.zipURL = zipURL
        self.isLegacySecureDFU = isLegacySecureDFU
        self.notes = notes
    }

    /// Whether a device on `current` should be offered this release: strictly newer, the device
    /// meets the minimum, and the bootloader speaks SMP (MCUboot).
    public func isUpdate(from current: String?) -> Bool {
        guard !isLegacySecureDFU, let current = FirmwareVersion(current), let latest = FirmwareVersion(version) else { return false }
        if let minimum = FirmwareVersion(minVersion), current < minimum { return false }
        return latest > current
    }
}
