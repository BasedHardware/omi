import ContextCore
import Foundation

struct ContextSentryHandledReport: Sendable, Equatable {
    var area: ContextFallbackArea
    var outcome: ContextFallbackOutcome
    var reason: AnalyticsEvent.FallbackReason

    var message: String {
        "cfc-fallback area=\(area.rawValue) reason=\(reason.rawValue) outcome=\(outcome.rawValue)"
    }

    var fingerprint: [String] { ["cfc-fallback", area.rawValue, reason.rawValue] }
    var tags: [String: String] { ["app": ContextSentryPolicy.appTag] }
}

protocol ContextSentryReporting: Sendable {
    func send(_ report: ContextSentryHandledReport)
    func close()
}

/// Additional invalidation for fail-closed configuration loads and failed settings writes.
/// The normal cross-launch boundary is the generation persisted in ExclusionConfiguration.
/// This record is outside the SDK subtree, so late SDK writes cannot erase it.
struct ContextSentryRetirement: Sendable {
    static let key = "context.sentry.cacheRetired"
    let defaults: UserDefaults

    func mark() {
        defaults.set(true, forKey: Self.key)
        defaults.synchronize()
    }

    var isRetired: Bool { defaults.bool(forKey: Self.key) }

    func clear() {
        defaults.removeObject(forKey: Self.key)
        defaults.synchronize()
    }
}

/// Owns SDK startup and shutdown. Healthy crashes survive a relaunch in the same persisted
/// generation; an Airgap transition changes that generation before observers are notified.
/// The admission gate closes synchronously; SDK shutdown and cache cleanup follow off-thread.
final class ContextSentry: @unchecked Sendable {
    static let shared = ContextSentry(
        dsn: { ContextSentryConfig.dsn() },
        isShippingBundle: { ContextPaths.isShippingBundle },
        isSuppressed: { NetworkEgress.isSuppressed(.crashReporting) },
        cacheGeneration: { ExclusionEngine.shared.prepareCrashReportingGeneration() },
        cacheRoot: ContextSentryConfig.cacheDirectory(),
        retirement: ContextSentryRetirement(defaults: .standard),
        makeReporting: { SentrySDKReporting(options: $0) },
        registerAirgapObserver: { handler in
            ExclusionEngine.shared.addObserver { set in handler(set.airgapMode) }
        })

    enum State: Equatable {
        case disabled(DisabledReason)
        case started
        case closedByAirgap
    }

    enum DisabledReason: Equatable {
        case notShipping
        case missingConfig
        case airgappedAtLaunch
        case cacheWipeFailed
        case generationUnavailable
    }

    struct StartOptions: Sendable, Equatable {
        var dsn: String
        var releaseName: String
        var dist: String
        var environment: String
        var cacheRoot: String
    }

    private let lock = NSLock()
    private var didAttemptStart = false
    private var state: State = .disabled(.missingConfig)
    private var reporting: ContextSentryReporting?
    private var observerToken: UUID?
    private let dsn: () -> String?
    private let isShippingBundle: () -> Bool
    private let isSuppressed: () -> Bool
    private let cacheGeneration: () -> UUID?
    private let cacheRoot: URL
    private let retirement: ContextSentryRetirement
    private let makeReporting: (StartOptions) -> ContextSentryReporting
    private let registerAirgapObserver: (@Sendable (Bool) -> Void) -> UUID
    private let airgapQueue: DispatchQueue

    init(
        dsn: @escaping () -> String?,
        isShippingBundle: @escaping () -> Bool,
        isSuppressed: @escaping () -> Bool,
        cacheGeneration: @escaping () -> UUID?,
        cacheRoot: URL,
        retirement: ContextSentryRetirement,
        makeReporting: @escaping (StartOptions) -> ContextSentryReporting,
        registerAirgapObserver: @escaping (@Sendable (Bool) -> Void) -> UUID,
        airgapQueue: DispatchQueue = DispatchQueue(
            label: "com.omi.context-for-claude.sentry", qos: .utility)
    ) {
        self.dsn = dsn
        self.isShippingBundle = isShippingBundle
        self.isSuppressed = isSuppressed
        self.cacheGeneration = cacheGeneration
        self.cacheRoot = cacheRoot
        self.retirement = retirement
        self.makeReporting = makeReporting
        self.registerAirgapObserver = registerAirgapObserver
        self.airgapQueue = airgapQueue
    }

    func start() {
        lock.lock()
        defer { lock.unlock() }
        guard !didAttemptStart else { return }
        didAttemptStart = true
        guard isShippingBundle() else {
            state = .disabled(.notShipping)
            return
        }
        guard let projectDSN = ContextSentryConfig.dsn(dsn()) else { return }

        // Register before selecting a generation: even an on/off toggle during startup must
        // permanently close this process's gate. The callback never takes the lifecycle lock.
        observerToken = registerAirgapObserver { [weak self] airgapMode in
            if airgapMode { self?.closeForAirgap() }
        }
        guard !isSuppressed(), !ContextSentryGate.isClosed else {
            ContextSentryGate.enterAirgap()
            retirement.mark()
            _ = wipeCache()
            state = .disabled(.airgappedAtLaunch)
            NetworkEgress.recordSuppression(.crashReporting, outcome: .dropped)
            return
        }
        guard let generation = cacheGeneration() else {
            state = .disabled(.generationUnavailable)
            return
        }
        let activeCache = cacheRoot.appendingPathComponent(generation.uuidString, isDirectory: true)
        guard prepareCache(keeping: activeCache) else {
            state = .disabled(.cacheWipeFailed)
            ContextLog.error("sentry cache cleanup failed; reporting disabled", "sentry")
            return
        }
        guard !isSuppressed(), !ContextSentryGate.isClosed else {
            state = .disabled(.airgappedAtLaunch)
            return
        }
        let identity = ContextSentryConfig.releaseIdentity()
        reporting = makeReporting(StartOptions(
            dsn: projectDSN, releaseName: identity.releaseName, dist: identity.dist,
            environment: "production", cacheRoot: activeCache.path))
        state = .started
    }

    func report(_ handled: ContextSentryHandledReport) {
        lock.lock()
        let reporting = self.reporting
        lock.unlock()
        guard !isSuppressed(), !ContextSentryGate.isClosed else { return }
        reporting?.send(handled)
    }

    var isStarted: Bool { currentState == .started }

    var currentState: State {
        lock.lock(); defer { lock.unlock() }
        return state
    }

    private func closeForAirgap() {
        ContextSentryGate.enterAirgap()
        retirement.mark()
        airgapQueue.async { [weak self] in
            guard let self else { return }
            // Startup holds this lock through cache selection and SDK publication, so cleanup
            // cannot race startup into clearing retirement or installing a handler after close.
            self.lock.lock()
            let reporting = self.reporting
            self.reporting = nil
            if reporting != nil { self.state = .closedByAirgap }
            self.lock.unlock()
            _ = self.wipeCache()
            reporting?.close()
            _ = self.wipeCache()
        }
    }

    private func prepareCache(keeping active: URL) -> Bool {
        // Retirement also covers fail-closed loads where no persisted generation was available.
        if retirement.isRetired {
            guard wipeCache() else { return false }
            retirement.clear()
        }
        do {
            let manager = FileManager.default
            if manager.fileExists(atPath: cacheRoot.path) {
                for child in try manager.contentsOfDirectory(
                    at: cacheRoot, includingPropertiesForKeys: nil)
                where child.lastPathComponent != active.lastPathComponent {
                    try manager.removeItem(at: child)
                }
            }
            try manager.createDirectory(
                at: active, withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700])
            return true
        } catch {
            return false
        }
    }

    private func wipeCache() -> Bool {
        let manager = FileManager.default
        guard manager.fileExists(atPath: cacheRoot.path) else { return true }
        do {
            try manager.removeItem(at: cacheRoot)
            return !manager.fileExists(atPath: cacheRoot.path)
        } catch {
            return false
        }
    }
}
