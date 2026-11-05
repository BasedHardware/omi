import Foundation
import OmiCore
import OmiNetwork

public extension FakeAPIClient {
    /// `latestFirmwareRelease` when it is newer than `firmware`; `nil` otherwise, like the backend's 404.
    func latestFirmware(model: String, firmware: String, hardware _: String?, manufacturer _: String?) async throws -> FirmwareRelease? {
        try lock.withLock {
            if let _error { throw _error }
            firmwareChecks.append("\(model)@\(firmware)")
            guard let release = latestFirmwareRelease,
                  let latest = FirmwareVersion(release.version), let current = FirmwareVersion(firmware), latest > current
            else { return nil }
            return release
        }
    }
}

public extension Fixtures {
    static let firmwareRelease = FirmwareRelease(
        version: "3.0.22", minVersion: "3.0.6",
        zipURL: URL(string: "https://github.com/BasedHardware/omi/releases/download/Omi_CV1_v3.0.22/Omi_CV1_OTA_v3.0.22.zip")!,
        isLegacySecureDFU: false, notes: "Fix audio sync issue"
    )
}
