import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// Apple Health, read only (behind a seam: HealthKit in the app, a fake in tests).
public protocol HealthDataReading: Sendable {
    var isAvailable: Bool { get }
    /// Shows the HealthKit sheet; `true` once it was shown (HealthKit never says what was allowed).
    func requestAuthorization() async -> Bool
    /// Any sample readable in the last 90 days: the only way to tell "allowed" from "denied".
    func probeAccess() async -> Bool
    func summary(days: Int) async -> HealthSummary?
}

/// Settings › Capabilities › Apple Health (Flutter `apple_health_detail_page`, `apple_health_service.dart`):
/// connect asks HealthKit, checks that something is readable, syncs the last 7 days to
/// `PUT v1/integrations/apple-health/sync` and marks the integration connected. While connected,
/// the summary is synced again when the app comes back (Flutter syncs when the chat opens).
@MainActor
@Observable
public final class AppleHealthStore {
    public enum Phase: Equatable, Sendable { case idle, connecting, disconnecting }
    public enum Notice: Equatable, Sendable { case connected, denied, unavailable, failed, disconnected, disconnectFailed }

    public static let key = "apple_health"
    static let periodDays = 7
    /// At most one automatic sync per this interval.
    static let autoSyncInterval: TimeInterval = 60 * 60

    public private(set) var isConnected = false
    public private(set) var lastSync: Date?
    public private(set) var phase = Phase.idle
    /// What the last connect / disconnect came to; the screen shows it once.
    public var notice: Notice?

    private let api: any APIClientProtocol
    private let reader: any HealthDataReading
    private let preferences: Preferences
    private let now: () -> Date
    /// When `syncIfConnected` last asked the backend.
    private var lastCheck: Date?

    public init(
        api: any APIClientProtocol, reader: any HealthDataReading, preferences: Preferences, now: @escaping () -> Date = Date.init
    ) {
        self.api = api
        self.reader = reader
        self.preferences = preferences
        self.now = now
        lastSync = preferences.string(.healthLastSync).flatMap(Double.init).map(Date.init(timeIntervalSince1970:))
    }

    public var isAvailable: Bool {
        reader.isAvailable
    }

    private var integration: Integration {
        Integration(id: Self.key, kind: .integration, isConnected: isConnected)
    }

    /// `GET v1/integrations/apple_health`.
    public func load() async {
        if let connected = try? await api.integrationConnected(Self.key) { isConnected = connected }
    }

    public func connect() async {
        guard phase == .idle else { return }
        guard reader.isAvailable else {
            notice = .unavailable
            return
        }
        phase = .connecting
        defer { phase = .idle }
        guard await reader.requestAuthorization(), await reader.probeAccess() else {
            notice = .denied
            return
        }
        // The connection stands even when the first sync fails (Flutter logs and carries on).
        _ = await sync()
        do {
            try await api.markAppleHealthConnected()
            isConnected = true
            notice = .connected
        } catch {
            notice = .failed
        }
    }

    public func disconnect() async {
        guard phase == .idle else { return }
        phase = .disconnecting
        defer { phase = .idle }
        do {
            try await api.disconnectIntegration(integration)
            isConnected = false
            notice = .disconnected
        } catch {
            notice = .disconnectFailed
        }
    }

    /// The last 7 days to the backend; `false` when nothing was readable or the upload failed.
    @discardableResult
    public func sync() async -> Bool {
        guard let summary = await reader.summary(days: Self.periodDays), summary.hasData else { return false }
        let date: Date
        do {
            date = try await api.syncAppleHealth(summary) ?? now()
        } catch {
            return false
        }
        lastSync = date
        preferences.set(String(date.timeIntervalSince1970), for: .healthLastSync)
        return true
    }

    /// Back in the app: a fresh summary while connected, at most once an hour.
    public func syncIfConnected() async {
        guard reader.isAvailable, phase == .idle else { return }
        let recent = [lastSync, lastCheck].compactMap(\.self).max()
        if let recent, now().timeIntervalSince(recent) < Self.autoSyncInterval { return }
        lastCheck = now()
        await load()
        guard isConnected else { return }
        await sync()
    }
}
