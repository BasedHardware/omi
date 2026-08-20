import ContextCore
import Foundation

/// Where analytics events go, and the rules for getting them there.
///
/// An actor because events arrive from every part of the app — the capture threads, the main-actor
/// UI, the update delegate — and the spool is a single mutable buffer backed by one file. Serialising
/// through an actor is the difference between "a counter" and "a data race in a menu-bar app".
///
/// ## Batching, and why it is not optional
///
/// One HTTP request per event would be absurd for a ~10-events-a-day app and, worse, would make the
/// app's network fingerprint follow the user's activity in real time: a request the moment a
/// recording starts, another the moment a search runs. Batching on a timer decouples *when we send*
/// from *what the person just did*, which is a privacy property, not only an efficiency one.
///
/// ## Failure
///
/// Sending is best-effort forever. A failed flush leaves events in the spool for the next one; a
/// spool that grows past its cap drops its oldest events. Analytics must never retry hard enough to
/// matter, never block a user action, and never surface an error — an app that shows someone a
/// dialog because a metric did not upload has its priorities inverted.
actor AnalyticsSink {

    /// PostHog's *project* token. Public by design — it can only write events into this project, and
    /// it ships in the Omi macOS app's binary already (`desktop/macos/Desktop/Sources/PostHogManager.swift`).
    /// It is not a secret and must not be treated as one; it is also not a personal API key and can
    /// read nothing.
    ///
    /// The same project as the Omi app on purpose: one place to query, and the existing dashboards
    /// and the analytics runbook already point at it. Separation between the two products is by
    /// `cfc_` event prefix and the `app` property — see `AnalyticsPayload.superProperties`.
    static let projectToken = "phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y"
    static let endpoint = URL(string: "https://us.i.posthog.com/batch/")!

    /// How long a batch waits for more company before going up.
    static let flushInterval: TimeInterval = 60

    /// Past this, the oldest events are dropped. Sized for an app that is offline for a week and
    /// still fits in a file nobody would notice.
    static let spoolCapacity = 500

    /// One request never carries more than this, so a spool that grew while offline drains over
    /// several flushes rather than in one implausible burst.
    static let batchSize = 50

    static let shared = AnalyticsSink()

    private var spool: [AnalyticsPayload] = []
    private var flushTask: Task<Void, Never>?
    private let spoolURL: URL
    private let transport: AnalyticsTransport
    /// Injected so a test can drive the *scheduled* path in milliseconds. The scheduled path is not
    /// a faster version of the direct one — it is the only path production ever takes while the app
    /// is running, and it was broken in 1.0.13 precisely because nothing exercised it.
    private let flushInterval: TimeInterval

    /// `transport` and `spoolURL` are injected so tests drive the whole path — spool, batch, retry,
    /// drop — without a network and without touching the real support directory.
    init(
        spoolURL: URL = ContextPaths.supportDirectory.appendingPathComponent("analytics-spool.json"),
        transport: AnalyticsTransport = URLSessionAnalyticsTransport(),
        flushInterval: TimeInterval = AnalyticsSink.flushInterval
    ) {
        self.spoolURL = spoolURL
        self.transport = transport
        self.flushInterval = flushInterval
        self.spool = Self.loadSpool(from: spoolURL)
    }

    /// Queues one event.
    ///
    /// **Airgap Mode is checked by the caller, not here.** `ContextAnalytics.record` drops the event
    /// before it ever reaches the spool, because spooling an airgapped event and uploading it when
    /// the switch goes off would be the disclosure the switch exists to prevent, merely delayed.
    func enqueue(_ payload: AnalyticsPayload) {
        spool.append(payload)
        if spool.count > Self.spoolCapacity {
            // Oldest first. A spool that has overflowed has already lost the argument about
            // completeness; keeping the *recent* events at least keeps the series current.
            spool.removeFirst(spool.count - Self.spoolCapacity)
        }
        persist()
        scheduleFlush()
    }

    /// Sends everything queued, oldest first, in batches.
    ///
    /// Events are removed from the spool only after the transport reports success. A crash between
    /// send and persist re-sends a batch, which PostHog tolerates; the opposite ordering would lose
    /// events silently, which it cannot.
    func flush() async {
        // Cancels a *pending* timer, never the caller.
        //
        // **This is the bug that shipped in 1.0.13.** The scheduled task's body called this method,
        // whose first line cancelled `flushTask` — itself. `URLSession.data(for:)` honours task
        // cancellation, so the very next `await` threw, `send` reported the batch unsent, and the
        // spool grew forever. The app talked to `api.omi.me` all day and delivered no analytics at
        // all. Nothing caught it because every test called `flush()` directly, where `flushTask` is
        // nil and the cancel is a no-op — the scheduled path, the only one production takes while
        // running, had no coverage.
        flushTask?.cancel()
        flushTask = nil
        await drain()
    }

    /// Sends everything queued. Assumes any pending timer has already been dealt with by the caller,
    /// which is what keeps the scheduled task from cancelling itself.
    private func drain() async {
        // Whoever is draining now owns the queue, so a later `enqueue` is free to schedule again.
        flushTask = nil

        while !spool.isEmpty {
            let batch = Array(spool.prefix(Self.batchSize))
            let sent = await transport.send(batch, token: Self.projectToken, to: Self.endpoint)
            guard sent else { return }
            spool.removeFirst(batch.count)
            persist()
        }
    }

    #if DEBUG
    /// Test seams. The spool is private because nothing in the app has any business reading it; the
    /// tests need to, because "did a failed send keep the events?" is not observable any other way.
    var spooledCountForTesting: Int { spool.count }
    var oldestSpooledTimestampForTesting: Date? { spool.first?.timestamp }
    #endif

    private func scheduleFlush() {
        guard flushTask == nil else { return }
        flushTask = Task { [weak self] in
            guard let self else { return }
            try? await Task.sleep(nanoseconds: UInt64(await self.flushInterval * 1_000_000_000))
            guard !Task.isCancelled else { return }
            // `drain()`, not `flush()`: this *is* the scheduled task, and `flush()` would cancel it.
            await self.drain()
        }
    }

    // MARK: - Durability

    /// The spool survives relaunch, so events recorded seconds before a quit are not lost.
    ///
    /// Whole-file rewrite rather than an append log: at ten events a day the file is under a
    /// kilobyte, and a rewrite cannot leave a half-written trailing record that the next launch has
    /// to decide whether to trust.
    private func persist() {
        guard let data = try? JSONSerialization.data(withJSONObject: spool.map(\.json)) else { return }
        try? ContextPaths.ensureSupportDirectory(at: spoolURL.deletingLastPathComponent())
        try? data.write(to: spoolURL, options: .atomic)
        ContextPaths.setPermissions(spoolURL, mode: 0o600)
    }

    /// Anything unreadable is discarded rather than repaired. A spool is not user data; the cost of
    /// losing it is one gap in a chart, and the cost of trusting a damaged one is inventing events.
    private static func loadSpool(from url: URL) -> [AnalyticsPayload] {
        guard let data = try? Data(contentsOf: url),
              let rows = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }
        return rows.compactMap(AnalyticsPayload.init(persisted:)).suffix(spoolCapacity)
    }
}

// MARK: - Transport

/// The one thing that touches the network, behind a protocol so every test in this area runs offline.
protocol AnalyticsTransport: Sendable {
    /// Returns true only if the batch was accepted. A `false` leaves the events spooled.
    func send(_ batch: [AnalyticsPayload], token: String, to endpoint: URL) async -> Bool
}

struct URLSessionAnalyticsTransport: AnalyticsTransport {
    /// Short, and shorter than the flush interval: a request still in flight when the next flush is
    /// due is a request that has already failed at being unobtrusive.
    static let timeout: TimeInterval = 20

    func send(_ batch: [AnalyticsPayload], token: String, to endpoint: URL) async -> Bool {
        guard !batch.isEmpty else { return true }

        let body: [String: Any] = ["api_key": token, "batch": batch.map(\.json)]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else {
            // Unencodable means a bug in the payload types, not a network problem. Reporting success
            // drops the batch, which is right: retrying it forever would wedge the spool behind an
            // event that can never be sent.
            ContextLog.info("[analytics] dropped an unencodable batch of \(batch.count)", "analytics")
            return true
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.httpBody = data
        request.timeoutInterval = Self.timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("context-for-claude-analytics/1.0", forHTTPHeaderField: "User-Agent")

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let consume = Self.shouldConsumeBatch(forStatus: status)
            if consume, !(200..<300).contains(status) {
                ContextLog.info("[analytics] dropped batch of \(batch.count) on HTTP \(status)", "analytics")
            }
            return consume
        } catch {
            return false
        }
    }

    /// Whether a response means "stop carrying these events", as a pure function of the status so the
    /// rule is testable without a server.
    ///
    /// A 4xx other than 429 will never succeed on retry — a malformed batch, or a revoked token — and
    /// **consuming it is the only way the spool ever empties again**. Keeping it would park every
    /// later event behind one that can never be sent. 429 is the exception because it is temporary,
    /// and 5xx is the server's problem, not the batch's.
    static func shouldConsumeBatch(forStatus status: Int) -> Bool {
        if (200..<300).contains(status) { return true }
        return (400..<500).contains(status) && status != 429
    }
}

// MARK: - Persistence round-trip

extension AnalyticsPayload {
    /// Rebuilds a spooled payload. Returns nil for anything that does not round-trip cleanly — a
    /// half-understood event is not worth sending.
    init?(persisted row: [String: Any]) {
        guard let name = row["event"] as? String,
              let rawProperties = row["properties"] as? [String: Any],
              let distinctID = rawProperties["distinct_id"] as? String,
              let stamp = row["timestamp"] as? String,
              let timestamp = ISO8601DateFormatter.analytics.date(from: stamp)
        else { return nil }

        var properties: [String: AnalyticsValue] = [:]
        for (key, value) in rawProperties where key != "distinct_id" {
            // Bool is checked first: `NSNumber` bridges both, and an `Int` case for a bool would
            // turn `signed_in: true` into `signed_in: 1` on the way back out of the spool.
            if let bool = value as? Bool { properties[key] = .bool(bool) }
            else if let int = value as? Int { properties[key] = .int(int) }
            else if let string = value as? String { properties[key] = .string(string) }
        }

        self.init(name: name, distinctID: distinctID, timestamp: timestamp, properties: properties)
    }

    /// Memberwise init for the spool round-trip, kept private to this file's concern so the ordinary
    /// construction path stays the one that cannot forget super-properties.
    fileprivate init(
        name: String,
        distinctID: String,
        timestamp: Date,
        properties: [String: AnalyticsValue]
    ) {
        self.name = name
        self.distinctID = distinctID
        self.timestamp = timestamp
        self.properties = properties
    }
}
