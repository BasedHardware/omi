import Foundation
import Observation
import OmiNetwork

/// Plan & usage beyond the quota (Flutter `usage_page`, `fair_use_page`): words, insights and
/// memories per period, and the fair-use standing.
@MainActor
@Observable
public final class UsageStore {
    public var period: UsageStats.Period = .monthly
    public private(set) var stats: [UsageStats.Period: UsageStats] = [:]
    public private(set) var fairUse: FairUseStatus?
    public private(set) var failedPeriods: Set<UsageStats.Period> = []
    public private(set) var fairUseFailed = false

    private let api: any APIClientProtocol
    private let timeZone: String

    public init(api: any APIClientProtocol, timeZone: String = TimeZone.current.identifier) {
        self.api = api
        self.timeZone = timeZone
    }

    public var current: UsageStats? {
        stats[period]
    }

    public func load(_ period: UsageStats.Period? = nil) async {
        let period = period ?? self.period
        do {
            stats[period] = try await api.usage(period: period, timeZone: timeZone)
            failedPeriods.remove(period)
        } catch {
            failedPeriods.insert(period)
        }
    }

    public func loadFairUse() async {
        do {
            fairUse = try await api.fairUseStatus()
            fairUseFailed = false
        } catch {
            fairUseFailed = true
        }
    }
}

/// Profile and data: invite link, apps that read your data, export, cancel subscription, and
/// keeping audio on the phone (Flutter `profile`, `data_privacy_page`, `data_export`,
/// `cancel_subscription_sheet`, `local_storage_page`).
@MainActor
@Observable
public final class ProfileStore {
    public enum ExportPhase: Equatable, Sendable { case idle, exporting, ready(URL), failed }

    public private(set) var referralURL: URL?
    public private(set) var referralFailed = false
    public private(set) var appsWithAccess: [AppDataAccess]?
    public private(set) var exportPhase: ExportPhase = .idle
    public private(set) var lastError: String?

    private let api: any APIClientProtocol
    private let defaults: UserDefaults
    private var exportTask: Task<Void, Never>?
    /// Flutter's key (`unlimitedLocalStorageEnabled`), so an update keeps the choice.
    static let audioOnPhoneKey = "flutter.unlimitedLocalStorageEnabled"

    public init(api: any APIClientProtocol, defaults: UserDefaults = .standard) {
        self.api = api
        self.defaults = defaults
        storesAudioOnPhone = defaults.bool(forKey: Self.audioOnPhoneKey)
    }

    /// Keep every recording on this iPhone, not only the ones that have not reached the cloud yet.
    public var storesAudioOnPhone: Bool {
        didSet { defaults.set(storesAudioOnPhone, forKey: Self.audioOnPhoneKey) }
    }

    public func loadReferral() async {
        do {
            referralURL = try await api.referralURL()
            referralFailed = referralURL == nil
        } catch {
            referralFailed = true
        }
    }

    public func loadAppsWithAccess() async {
        appsWithAccess = (try? await api.appsWithDataAccess()) ?? appsWithAccess ?? []
    }

    /// Downloads everything Omi stores; `cancelExport()` stops it.
    public func export() {
        exportTask?.cancel()
        exportPhase = .exporting
        exportTask = Task { [weak self, api] in
            let result = try? await api.exportAllData()
            guard let self, !Task.isCancelled else {
                if let result { try? FileManager.default.removeItem(at: result.deletingLastPathComponent()) }
                return
            }
            exportPhase = result.map { .ready($0) } ?? .failed
        }
    }

    public func cancelExport() {
        exportTask?.cancel()
        exportTask = nil
        exportPhase = .idle
    }

    /// The share sheet closed: the temporary copy goes.
    public func finishExport() {
        if case let .ready(url) = exportPhase { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        exportPhase = .idle
    }

    /// Stripe cancels at the end of the billing period. Returns whether the backend took it.
    public func cancelSubscription(reason: String?, details: String?) async -> Bool {
        lastError = nil
        do {
            try await api.cancelSubscription(reason: reason, details: details?.trimmingCharacters(in: .whitespacesAndNewlines))
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }
}
