import Foundation
import Observation
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence

/// What the firmware update needs from the device side (real: `DeviceStore`; tests: a fake).
@MainActor
public protocol FirmwareDeviceHost: AnyObject {
    var paired: PairedDevice? { get }
    var connection: DeviceStore.Connection { get }
    var battery: Int? { get }
    /// The firmware revision read on the current connection.
    var liveFirmware: String? { get }
    func suspendForFirmwareUpdate()
    func resumeAfterFirmwareUpdate()
}

extension DeviceStore: FirmwareDeviceHost {}

/// Omi firmware updates, kept to one row in My Devices: checks the backend when the Omi connects
/// (at most once a day), and on the user's confirmation downloads, flashes and waits for the Omi
/// to come back on the new version. No rollback, no channels (PLAN.md §4.5).
@MainActor
@Observable
public final class FirmwareStore {
    public enum Phase: Equatable, Sendable {
        case idle
        case downloading
        /// Upload progress, 0...1.
        case installing(Double)
        /// Flashed; the Omi restarts and reconnects on its own.
        case restarting
        case finished(version: String)
        case failed(Failure)
    }

    public enum Failure: Equatable, Sendable { case lowBattery, notConnected, download, install }

    /// The update on offer for the paired Omi, if any.
    public private(set) var available: FirmwareRelease?
    public private(set) var phase: Phase = .idle

    /// An update may only start at this battery level or above.
    public static let minimumBattery = 20
    static let checkInterval: TimeInterval = 24 * 60 * 60
    /// A failed check (offline, backend down) is retried on a later connect, not on every read.
    static let retryInterval: TimeInterval = 10 * 60

    /// The last check, persisted so a relaunch does not ask again the same day.
    struct Check: Codable, Equatable {
        var deviceID: String
        var firmware: String
        var checkedAt: Date
        var release: FirmwareRelease?
    }

    private let api: any APIClientProtocol
    private let updater: any FirmwareUpdating
    private let download: @Sendable (URL) async throws -> URL
    private let preferences: Preferences
    private let now: () -> Date
    private let handOverDelay: Duration
    @ObservationIgnored private weak var devices: (any FirmwareDeviceHost)?
    @ObservationIgnored private var checking = false
    @ObservationIgnored private var lastFailedCheck: Date?
    @ObservationIgnored private var target: FirmwareVersion?

    public init(
        api: any APIClientProtocol,
        devices: any FirmwareDeviceHost,
        updater: any FirmwareUpdating,
        preferences: Preferences,
        download: @escaping @Sendable (URL) async throws -> URL = FirmwareStore.downloadPackage,
        now: @escaping () -> Date = Date.init,
        handOverDelay: Duration = .seconds(2)
    ) {
        self.api = api
        self.devices = devices
        self.updater = updater
        self.preferences = preferences
        self.download = download
        self.now = now
        self.handOverDelay = handOverDelay
    }

    public var isBusy: Bool {
        switch phase {
        case .downloading, .installing, .restarting: true
        default: false
        }
    }

    /// Device info arrived (wired to `DeviceStore.onDeviceInfo`): finishes a pending update or
    /// checks for one.
    public func deviceInfoChanged() {
        guard let devices, let firmware = devices.liveFirmware else { return }
        if phase == .restarting, let target {
            // MCUboot keeps the old image when the new one does not boot.
            if let running = FirmwareVersion(firmware), running >= target {
                phase = .finished(version: firmware)
                available = nil
            } else {
                phase = .failed(.install)
            }
            self.target = nil
            return
        }
        Task { await checkIfDue() }
    }

    /// Asks the backend for a newer firmware unless it was asked for this device and version
    /// within the last day.
    public func checkIfDue() async {
        guard !checking, !isBusy, let devices, let device = devices.paired, let model = device.modelNumber,
              let firmware = devices.liveFirmware, FirmwareVersion(firmware) != nil else { return }
        if let cached = cachedCheck(), cached.deviceID == device.id, cached.firmware == firmware,
           now().timeIntervalSince(cached.checkedAt) < Self.checkInterval
        {
            available = cached.release.flatMap { $0.isUpdate(from: firmware) ? $0 : nil }
            return
        }
        if let lastFailedCheck, now().timeIntervalSince(lastFailedCheck) < Self.retryInterval { return }
        checking = true
        defer { checking = false }
        do {
            let release = try await api.latestFirmware(
                model: model, firmware: firmware, hardware: device.hardwareRevision, manufacturer: device.manufacturerName
            )
            lastFailedCheck = nil
            let check = Check(deviceID: device.id, firmware: firmware, checkedAt: now(), release: release)
            preferences.set((try? JSONEncoder().encode(check)).flatMap { String(data: $0, encoding: .utf8) }, for: .firmwareCheck)
            available = release.flatMap { $0.isUpdate(from: firmware) ? $0 : nil }
        } catch {
            lastFailedCheck = now()
        }
    }

    /// Runs the update. Only ever called from the confirmation the user tapped; refuses below
    /// `minimumBattery` or without a connected Omi.
    public func install() async {
        guard !isBusy, let release = available, let devices,
              let id = devices.paired.flatMap({ UUID(uuidString: $0.id) }) else { return }
        guard devices.connection == .connected else {
            phase = .failed(.notConnected)
            return
        }
        guard let battery = devices.battery, battery >= Self.minimumBattery else {
            phase = .failed(.lowBattery)
            return
        }
        phase = .downloading
        let package: URL
        do {
            package = try await download(release.zipURL)
        } catch {
            phase = .failed(.download)
            return
        }
        devices.suspendForFirmwareUpdate()
        try? await Task.sleep(for: handOverDelay)
        phase = .installing(0)
        do {
            for try await progress in updater.update(deviceID: id, package: package) {
                phase = .installing(progress)
            }
        } catch {
            try? FileManager.default.removeItem(at: package)
            devices.resumeAfterFirmwareUpdate()
            phase = .failed(.install)
            return
        }
        try? FileManager.default.removeItem(at: package)
        target = FirmwareVersion(release.version)
        preferences.set(nil as String?, for: .firmwareCheck)
        phase = .restarting
        devices.resumeAfterFirmwareUpdate()
    }

    /// Back to the update row after a failure or a finished update.
    public func dismissResult() {
        guard !isBusy else { return }
        phase = .idle
    }

    private func cachedCheck() -> Check? {
        guard let data = preferences.string(.firmwareCheck)?.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(Check.self, from: data)
    }

    /// Downloads the OTA package into Caches, keeping the `.zip` extension the DFU library reads.
    public nonisolated static let downloadPackage: @Sendable (URL) async throws -> URL = { url in
        let (file, response) = try await URLSession.shared.download(from: url)
        guard let http = response as? HTTPURLResponse, (200 ..< 300).contains(http.statusCode) else {
            throw APIError.http(status: (response as? HTTPURLResponse)?.statusCode ?? 0, body: "")
        }
        let caches = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let fileExtension = url.pathExtension.isEmpty ? "zip" : url.pathExtension
        let destination = caches.appending(path: "omi-firmware-\(UUID().uuidString).\(fileExtension)")
        try FileManager.default.moveItem(at: file, to: destination)
        return destination
    }
}
