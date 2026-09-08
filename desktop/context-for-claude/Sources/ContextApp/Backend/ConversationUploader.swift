import Combine
import ContextCore
import Foundation

/// Pushes finished local sessions into the user's real Omi account.
///
/// **Why `POST v1/conversations/from-segments` and not only relying on `/v4/listen`.** Live
/// capture already streams audio to `/v4/listen` for cloud STT (and, on Apple Silicon, also runs
/// on-device Parakeet in parallel). Finished sessions in `context.db` still need a durable,
/// retryable upload into the account: from-segments accepts transcript lines that arrived from
/// either path, the explicit-finalize path websocket sessions end through is capped at 10
/// conversations an hour (`conversations:create`) while from-segments allows 30
/// (`conversations:from-segments`), and from-segments is a plain request that either succeeded or
/// did not — a queue can retry it, which is not true of a stream.
///
/// **Why `source: "phone"`.** It is the source the backend treats as "a transcript arrived,
/// process it": memories are extracted immediately. `"desktop"` can defer that extraction until
/// the user first opens the conversation, and a conversation that silently never produces memories
/// is worse than no upload at all.
///
/// The deferral is a *cost policy*, not a property of the source: `should_defer_desktop_processing`
/// only defers for accounts on the free desktop tier without BYOK, so a desktop-entitled plan
/// (Operator / Architect) runs the identical pipeline under either source. `"desktop"` is therefore
/// not an escape hatch from a backend refusal that happens during processing — verified live: while
/// the backend answered `503 Memory writes are globally paused`, one real session posted as
/// `"desktop"` got the same 503, because `process_conversation` reaches the same fail-closed
/// `_extract_memories`. The trial paywall that source also opts into is off by default
/// (`TRIAL_PAYWALL_ENABLED`) and exempts desktop-entitled plans, so it is not the reason to avoid
/// `"desktop"` — the deferral is.
///
/// Everything else here follows from one rule: **nothing the user said is ever dropped.** Not while
/// they are signed out, not across a crash, not when the backend is down. The queue is on disk
/// (`UploadQueue`), the idempotency key is derived rather than generated, and every failure path
/// ends in "try again later", never in "forget it".
@MainActor
final class ConversationUploader: ObservableObject {
    static let shared = ConversationUploader()

    /// When a conversation was last accepted by the backend. Restored from disk on launch.
    @Published private(set) var lastUploadedAt: Double?
    /// Sessions still owed to the account, due now or later.
    @Published private(set) var pendingCount: Int = 0
    /// The last failure, in a sentence a person can act on. Nil once something succeeds.
    @Published private(set) var lastError: String?

    // MARK: - Policy

    private static let category = "upload"
    private static let path = "v1/conversations/from-segments"

    /// One request every two minutes is exactly the 30/hour the endpoint allows, spent evenly.
    /// Charging at the limit and then sitting in a 429 backoff would upload strictly less.
    private static let throttleInterval: Double = 120
    private static let baseBackoff: Double = 30
    private static let maxBackoff: Double = 900
    /// How long an unfinished session is left alone before it is looked at again.
    private static let settleInterval: Double = 300
    /// The endpoint's own ceiling. A session with more lines becomes consecutive conversations.
    private static let maxSegmentsPerRequest = 500
    /// A backstop pass, so a wake-up missed across sleep/wake still happens eventually.
    private static let tickInterval: Double = 600

    private let database = UploadDatabase()
    private var isDraining = false
    private var didRestoreState = false
    /// Said once per airgapped stretch. The ticker drains every `tickInterval`, and a line per tick
    /// would turn a deliberate setting into a log flood.
    private var didLogAirgap = false
    /// Said once per launch, for the same reason: a queue this Mac cannot safely attribute is a
    /// standing condition, not an event.
    private var didLogForeignOwner = false
    private var wake: Task<Void, Never>?
    private var ticker: Task<Void, Never>?
    private var cancellables: Set<AnyCancellable> = []

    private init() {
        // Sessions captured while signed out are not dropped, they are parked — and this is what
        // un-parks them the moment there is an account to put them in.
        OmiAuth.shared.$isSignedIn
            .removeDuplicates()
            .filter { $0 }
            .sink { [weak self] _ in
                ContextLog.info("Signed in; draining the upload queue", ConversationUploader.category)
                Task { await self?.drain() }
            }
            .store(in: &cancellables)

        ticker = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                // The first pass is the relaunch resume: whatever the queue still holds is due the
                // moment this object exists.
                await self.drain()
                try? await Task.sleep(for: .seconds(Self.tickInterval))
            }
        }
    }

    // MARK: - API

    /// Called by `Engine` when a session closes. Enqueues it durably, then kicks the drain.
    ///
    /// Fire-and-forget on purpose: the caller is finishing a conversation, and an upload must never
    /// be in front of that.
    func enqueue(sessionId: Int64) {
        let ownerId = OmiAuth.shared.userId
        Task { [weak self] in
            guard let self else { return }
            do {
                try await self.database.perform { try UploadQueue.markPending($0, sessionId: sessionId, ownerId: ownerId) }
                ContextLog.info("Session \(sessionId) queued for upload", Self.category)
            } catch {
                // The session is still on disk and reconciliation will find it again; this is a
                // delay, not a loss.
                ContextLog.error(
                    "Could not queue session \(sessionId): \(error.localizedDescription)", Self.category)
            }
            await self.drain()
        }
    }

    /// Uploads everything pending, oldest first. Safe to call repeatedly and from anywhere: a second
    /// call while one is running returns immediately rather than racing it.
    func drain() async {
        guard !isDraining else { return }
        isDraining = true
        defer { isDraining = false }

        await restoreStateOnce()
        await reconcile()
        // Before the airgap and sign-in guards on purpose. Claiming is a local write about who the
        // queue's work belongs to; it needs an account, not a network, and a user in Airgap Mode
        // still deserves a `pendingCount` that means what it says.
        await claimQueuedBeforeSignIn()
        await refreshPendingCount()

        // Airgap Mode: the queue is durable across launches, so the honest answer is to leave every
        // entry exactly where it is rather than to dequeue, fail, or skip. Nothing is marked failed
        // either — `lastError` is what the menu bar renders as an upload problem, and a user's own
        // setting is not a problem the app should report as one. `pendingCount` keeps telling the
        // true story ("N conversations waiting to upload") and the Settings row explains why.
        guard !NetworkEgress.isSuppressed(.conversationUpload) else {
            if !didLogAirgap {
                didLogAirgap = true
                ContextLog.info(
                    "Airgap Mode on; \(pendingCount) session(s) stay queued on this Mac", Self.category)
                NetworkEgress.recordSuppression(.conversationUpload, outcome: .degraded)
            }
            // No wake is scheduled: the entries are already due and a timer for "try again in zero
            // seconds" is a spin. The periodic ticker picks the queue up once the switch goes off.
            return
        }
        didLogAirgap = false

        guard OmiAuth.shared.isSignedIn else {
            if pendingCount > 0 {
                ContextLog.info(
                    "\(pendingCount) session(s) queued, waiting for sign-in", Self.category)
            }
            return
        }

        // Entries that answered "not now" this pass. Without this the loop would keep picking the
        // same oldest entry and never reach the ones behind it.
        var blocked: Set<Int64> = []

        while !Task.isCancelled {
            guard let entry = await nextDue(excluding: blocked) else { break }

            let wait = await throttleWait()
            if wait > 0 {
                do {
                    try await Task.sleep(for: .seconds(wait))
                } catch {
                    return  // cancelled; the queue keeps everything
                }
            }
            guard OmiAuth.shared.isSignedIn else {
                ContextLog.info("Signed out mid-drain; the rest stays queued", Self.category)
                break
            }

            if case .stopped = await upload(entry) {
                blocked.insert(entry.sessionId)
            }
            await refreshPendingCount()
        }

        await refreshPendingCount()
        await scheduleNextWake()
    }

    // MARK: - One session

    private enum Outcome {
        /// The backend accepted something; move on and look again.
        case progressed
        /// Nothing more to do with this entry on this pass.
        case stopped
    }

    private func upload(_ entry: UploadQueue.Entry) async -> Outcome {
        let sessionId = entry.sessionId

        let content: UploadQueue.SessionUpload?
        do {
            content = try await database.perform { try UploadQueue.content($0, sessionId: sessionId) }
        } catch {
            ContextLog.error(
                "Could not read session \(sessionId): \(error.localizedDescription)", Self.category)
            return .stopped
        }
        guard let content else {
            await skip(sessionId, reason: "the local session no longer exists")
            return .stopped
        }

        // An open session is not a conversation yet. Uploading one would freeze a partial transcript
        // into a conversation that the idempotency key then prevents us from ever extending.
        guard content.isClosed else {
            await postpone(sessionId, seconds: Self.settleInterval, reason: "session still open")
            return .stopped
        }

        let parts = UploadPayload.parts(
            for: content,
            deviceIdHash: OmiAPI.deviceIdHash,
            maxSegments: Self.maxSegmentsPerRequest)
        guard !parts.isEmpty else {
            await skip(sessionId, reason: "no usable transcript lines")
            return .stopped
        }

        let index = max(0, min(entry.partsDone, parts.count))
        guard index < parts.count else {
            // Every part was accepted but the terminal mark never landed — a crash in the gap.
            await finish(sessionId, conversationIds: entry.conversationIds)
            return .progressed
        }
        let part = parts[index]

        // Stamped before the request, not after: a POST that leaves and never comes back still cost
        // the server a slot, and the throttle has to believe that.
        await stamp(.lastPostAt)

        do {
            let response = try await OmiAPI.shared.post(
                Self.path, body: part.body(language: Self.languageCode), as: UploadedConversation.self)

            let progress = parts.count > 1 ? " part \(index + 1)/\(parts.count)" : ""
            let discarded = response.discarded == true ? ", discarded by the server" : ""
            ContextLog.info(
                "Uploaded session \(sessionId)\(progress): \(part.segments.count) segments,"
                    + " \(Int(part.duration.rounded()))s → conversation \(response.id)"
                    + " [\(response.status ?? "unknown")]\(discarded)",
                Self.category)

            if index + 1 < parts.count {
                do {
                    try await database.perform {
                        try UploadQueue.markPartUploaded(
                            $0, sessionId: sessionId, partsDone: index + 1,
                            conversationId: response.id)
                    }
                } catch {
                    // The part is in the account; only our bookkeeping failed. Re-posting it later
                    // is harmless — the same client_session_id returns the same conversation.
                    ContextLog.error(
                        "Uploaded session \(sessionId) part \(index + 1) but could not record it:"
                            + " \(error.localizedDescription)", Self.category)
                    return .stopped
                }
                return .progressed
            }

            await finish(sessionId, conversationIds: entry.conversationIds + [response.id])
            return .progressed
        } catch {
            return await handle(error, sessionId: sessionId, attempts: entry.attempts)
        }
    }

    /// Turns one failure into a decision: retry when, or never.
    private func handle(_ error: Error, sessionId: Int64, attempts: Int) async -> Outcome {
        if error is CancellationError { return .stopped }

        let backoff = min(Self.maxBackoff, Self.baseBackoff * pow(2, Double(attempts)))

        guard let apiError = error as? OmiAPIError else {
            await fail(sessionId, reason: error.localizedDescription, retryIn: backoff)
            ContextLog.error(
                "Session \(sessionId) upload failed (\(error.localizedDescription));"
                    + " retrying in \(Int(backoff))s", Self.category)
            return .stopped
        }

        switch apiError {
        case .notSignedIn:
            await postpone(sessionId, seconds: 60, reason: "not signed in")
            ContextLog.info("Deferred session \(sessionId): not signed in", Self.category)
            return .stopped

        case .http(let status, let detail):
            switch status {
            case 429:
                // The server knows when it will be ready and we do not, so its own number wins.
                // `OmiAPI` folds `Retry-After` into the detail string, which is the only place a
                // header can reach a caller through `OmiAPIError`.
                let after = UploadPayload.retryAfterSeconds(in: detail) ?? backoff
                let delay = min(Self.maxBackoff, max(Self.throttleInterval, after))
                await fail(sessionId, reason: "rate limited", retryIn: delay)
                ContextLog.info(
                    "Deferred session \(sessionId): rate limited, retrying in \(Int(delay))s",
                    Self.category)
                return .stopped

            case 401, 403:
                // Credentials, not content. `OmiAPI` already tried one refresh.
                await postpone(sessionId, seconds: Self.settleInterval, reason: "not authorized")
                ContextLog.error("Deferred session \(sessionId): HTTP \(status)", Self.category)
                return .stopped

            case 400, 422:
                // The payload itself is wrong. The content never changes, so a retry would fail
                // identically and spend an hourly slot proving it.
                await skip(sessionId, reason: "rejected: \(detail)")
                return .stopped

            default:
                await fail(sessionId, reason: "HTTP \(status)", retryIn: status < 500 ? Self.maxBackoff : backoff)
                ContextLog.error(
                    "Session \(sessionId) upload failed with HTTP \(status); retrying later",
                    Self.category)
                return .stopped
            }

        default:
            // Transport, and a decode failure of an otherwise-successful response, are both worth
            // repeating: the request is idempotent, so at worst the retry gets the same
            // conversation id back.
            let reason = apiError.errorDescription ?? "\(apiError)"
            await fail(sessionId, reason: reason, retryIn: backoff)
            ContextLog.error(
                "Session \(sessionId) upload failed (\(reason)); retrying in \(Int(backoff))s",
                Self.category)
            return .stopped
        }
    }

    // MARK: - Queue state

    private func finish(_ sessionId: Int64, conversationIds: [String]) async {
        do {
            try await database.perform {
                try UploadQueue.markUploaded($0, sessionId: sessionId, conversationIds: conversationIds)
            }
        } catch {
            ContextLog.error(
                "Could not record session \(sessionId) as uploaded: \(error.localizedDescription)",
                Self.category)
        }
        let now = ContextTime.now
        lastUploadedAt = now
        lastError = nil
        await stamp(.lastUploadedAt, at: now)
    }

    private func fail(_ sessionId: Int64, reason: String, retryIn seconds: Double) async {
        lastError = reason
        do {
            try await database.perform {
                try UploadQueue.markFailed(
                    $0, sessionId: sessionId, error: reason, retryAt: ContextTime.now + seconds)
            }
        } catch {
            ContextLog.error(
                "Could not record the failure for session \(sessionId): \(error.localizedDescription)",
                Self.category)
        }
    }

    private func postpone(_ sessionId: Int64, seconds: Double, reason: String) async {
        try? await database.perform {
            try UploadQueue.postpone(
                $0, sessionId: sessionId, until: ContextTime.now + seconds, reason: reason)
        }
    }

    private func skip(_ sessionId: Int64, reason: String) async {
        ContextLog.info("Skipping session \(sessionId): \(reason)", Self.category)
        try? await database.perform { try UploadQueue.markSkipped($0, sessionId: sessionId, reason: reason) }
    }

    private func nextDue(excluding blocked: Set<Int64>) async -> UploadQueue.Entry? {
        // Signed in without a user id is not "signed in enough to upload": the queue records which
        // account each session is owed to, and a request sent now would put this Mac's capture in an
        // account we cannot name. Holding is the only safe answer, and saying so is what keeps it
        // from being another silent stall.
        guard let ownerId = OmiAuth.shared.userId else {
            ContextLog.error(
                "Signed in but the account has no user id; the queue stays put rather than uploading"
                    + " to an account this Mac cannot name", Self.category)
            return nil
        }
        do {
            let due = try await database.perform {
                try UploadQueue.pending($0, ownerId: ownerId, dueAt: ContextTime.now, limit: 20)
            }
            return due.first { !blocked.contains($0.sessionId) }
        } catch {
            ContextLog.error("Could not read the upload queue: \(error.localizedDescription)", Self.category)
            return nil
        }
    }

    /// Picks up sessions that closed without an `enqueue` — a crash in the gap, or a build where
    /// the engine never made the call. Bounded by a watermark set on first run, so installing this
    /// never decides to upload a month of history on its own.
    private func reconcile() async {
        let ownerId = OmiAuth.shared.userId
        do {
            let added = try await database.perform { try UploadQueue.reconcile($0, ownerId: ownerId) }
            if added > 0 {
                ContextLog.info("Queued \(added) closed session(s) found on disk", Self.category)
            }
        } catch {
            ContextLog.error("Reconcile failed: \(error.localizedDescription)", Self.category)
        }
    }

    /// Hands the queue's unattributed rows to the signed-in account, when the database can show
    /// nobody else has ever had capture on this Mac. See `UploadQueue.claimOrphans` for why that is
    /// the strongest evidence available and why a refusal is the right answer without it.
    private func claimQueuedBeforeSignIn() async {
        guard let ownerId = OmiAuth.shared.userId else { return }
        do {
            switch try await database.perform({ try UploadQueue.claimOrphans($0, ownerId: ownerId) }) {
            case .claimed(let count) where count > 0:
                ContextLog.info(
                    "Adopted \(count) session(s) that were queued before sign-in", Self.category)
            case .claimed:
                break
            case .refusedForeignOwner:
                // Once per launch: the drain runs every `tickInterval`, and this state does not
                // change on its own, so a line per pass would bury the log in a standing condition.
                guard !didLogForeignOwner else { break }
                didLogForeignOwner = true
                ContextLog.error(
                    "Sessions are queued with no account, and this Mac has already uploaded for a"
                        + " different one; they stay local rather than going to the wrong account",
                    Self.category)
            }
        } catch {
            ContextLog.error(
                "Could not adopt the sessions queued before sign-in: \(error.localizedDescription)",
                Self.category)
        }
    }

    private func refreshPendingCount() async {
        let ownerId = OmiAuth.shared.userId
        guard let count = try? await database.perform({ try UploadQueue.pendingCount($0, ownerId: ownerId) })
        else { return }
        if pendingCount != count { pendingCount = count }
    }

    /// Restores the throttle and the last-uploaded stamp from disk, once per launch.
    private func restoreStateOnce() async {
        guard !didRestoreState else { return }
        didRestoreState = true
        lastUploadedAt = await metaTimestamp(.lastUploadedAt)
    }

    private func metaTimestamp(_ key: UploadQueue.MetaKey) async -> Double? {
        guard let value = try? await database.perform({ try UploadQueue.timestamp($0, key) })
        else { return nil }
        return value
    }

    private func stamp(_ key: UploadQueue.MetaKey, at value: Double = ContextTime.now) async {
        try? await database.perform { try UploadQueue.setTimestamp($0, key, value) }
    }

    /// Seconds to hold before the next request, so the endpoint never sees more than one every
    /// `throttleInterval`. Survives a relaunch because the stamp is on disk.
    private func throttleWait() async -> Double {
        guard let last = await metaTimestamp(.lastPostAt) else { return 0 }
        return max(0, min(Self.throttleInterval, last + Self.throttleInterval - ContextTime.now))
    }

    /// Sleeps until the earliest waiting entry is due, then drains again. Replaces any earlier
    /// wake-up, so a queue with ten backed-off entries still schedules exactly one timer.
    private func scheduleNextWake() async {
        // `try?` on a throwing call returning `Double?` flattens to a single optional, so one
        // unwrap is both necessary and sufficient here.
        let ownerId = OmiAuth.shared.userId
        guard let dueAt = try? await database.perform({ try UploadQueue.nextDueAt($0, ownerId: ownerId) })
        else {
            return
        }
        let delay = dueAt - ContextTime.now
        guard delay > 0 else { return }

        wake?.cancel()
        wake = Task { [weak self] in
            try? await Task.sleep(for: .seconds(min(delay, Self.tickInterval)))
            guard !Task.isCancelled else { return }
            await self?.drain()
        }
    }

    /// ISO 639-1, because that is what the endpoint documents. Anything else becomes English rather
    /// than a 422 on a field nobody would think to look at.
    private static var languageCode: String {
        guard let code = Locale.current.language.languageCode?.identifier, code.count == 2 else {
            return "en"
        }
        return code.lowercased()
    }
}

// MARK: - Wire shapes

/// The request body of `POST v1/conversations/from-segments`.
///
/// Keys are spelled out rather than left to a key strategy: this is a contract with a server, and
/// it should not change because someone reconfigures an encoder.
private struct UploadRequestBody: Encodable {
    let transcriptSegments: [UploadSegmentBody]
    let clientSessionId: String
    let source: String
    let startedAt: String
    let finishedAt: String
    let language: String
    let clientDeviceId: String
    let clientPlatform: String

    enum CodingKeys: String, CodingKey {
        case transcriptSegments = "transcript_segments"
        case clientSessionId = "client_session_id"
        case source
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case language
        case clientDeviceId = "client_device_id"
        case clientPlatform = "client_platform"
    }
}

private struct UploadSegmentBody: Encodable {
    let text: String
    let speaker: String
    let speakerId: Int
    let isUser: Bool
    /// Seconds from the start of *this* conversation, never an epoch.
    let start: Double
    let end: Double

    enum CodingKeys: String, CodingKey {
        case text
        case speaker
        case speakerId = "speaker_id"
        case isUser = "is_user"
        case start
        case end
    }
}

private struct UploadedConversation: Decodable {
    let id: String
    let status: String?
    let discarded: Bool?
}

// MARK: - Payload

/// Turns a stored session into the requests the endpoint will accept.
///
/// Pure and free of any actor, so the rules the server enforces are in one readable place:
/// 1…500 segments, `end > start`, `start >= 0`, no blank text, `finished_at > started_at`.
private enum UploadPayload {

    struct Part {
        let clientSessionId: String
        let startedAt: Double
        let finishedAt: Double
        let segments: [UploadSegmentBody]

        var duration: Double { finishedAt - startedAt }

        func body(language: String) -> UploadRequestBody {
            UploadRequestBody(
                transcriptSegments: segments,
                clientSessionId: clientSessionId,
                // See the type doc: "phone" is the source that gets memories extracted now, and
                // "desktop" buys nothing when the backend refuses mid-processing.
                source: "phone",
                startedAt: UploadPayload.iso(startedAt),
                finishedAt: UploadPayload.iso(finishedAt),
                language: language,
                // The one id, not a second spelling of it assembled here. `build_client_device_id`
                // has to produce the same string from the headers that this body carries, or the
                // conversation is stored under a device that nothing else on the account is.
                clientDeviceId: ClientDevice.clientDeviceId,
                clientPlatform: ClientDevice.platform)
        }
    }

    /// The smallest span the server will accept between two timestamps. Parakeet can emit a line
    /// whose start and end round to the same instant, and a zero-length segment is a 422 that would
    /// cost the whole conversation.
    private static let minimumSpan: Double = 0.1

    /// Splits a session into consecutive uploads of at most `maxSegments` lines each.
    ///
    /// Each part is a conversation in its own right, so its times are relative to its own first
    /// line — except the first part, which starts at the session's own start when that is earlier,
    /// because that is when the conversation actually began.
    static func parts(
        for content: UploadQueue.SessionUpload, deviceIdHash: String, maxSegments: Int
    ) -> [Part] {
        let lines = content.lines
            .filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .sorted { $0.startedAt < $1.startedAt }
        guard !lines.isEmpty, maxSegments > 0 else { return [] }

        var parts: [Part] = []
        var index = 0
        var partNumber = 1

        while index < lines.count {
            let chunk = Array(lines[index..<min(index + maxSegments, lines.count)])
            let isFirst = index == 0
            let isLast = index + chunk.count >= lines.count

            var base = chunk[0].startedAt
            if isFirst { base = min(base, content.startedAt) }

            var segments: [UploadSegmentBody] = []
            segments.reserveCapacity(chunk.count)
            var latestEnd = base

            for line in chunk {
                let start = max(0, line.startedAt - base)
                var end = line.endedAt - base
                if end <= start { end = start + minimumSpan }
                segments.append(
                    UploadSegmentBody(
                        text: line.text.trimmingCharacters(in: .whitespacesAndNewlines),
                        // The mic is the user and the system tap is everyone else — the same
                        // attribution the rest of Context for Claude makes, in the shape the API expects.
                        speaker: line.isUser ? "SPEAKER_00" : "SPEAKER_01",
                        speakerId: line.isUser ? 0 : 1,
                        isUser: line.isUser,
                        start: start,
                        end: end))
                latestEnd = max(latestEnd, base + end)
            }

            var finishedAt = latestEnd
            if isLast { finishedAt = max(finishedAt, content.endedAt) }
            if finishedAt <= base { finishedAt = base + minimumSpan }

            parts.append(
                Part(
                    clientSessionId: clientSessionId(
                        deviceIdHash: deviceIdHash,
                        sessionId: content.sessionId,
                        sessionStartedAt: content.startedAt,
                        part: partNumber),
                    startedAt: base,
                    finishedAt: finishedAt,
                    segments: segments))

            index += chunk.count
            partNumber += 1
        }

        return parts
    }

    /// The idempotency key. `uuid5(uid, this)` is the conversation id the backend will use, so a
    /// retry after a crash, a timeout, or a 500 lands on the conversation that already exists
    /// instead of creating a second one.
    ///
    /// Three ingredients, and each is load-bearing:
    /// - the device hash, so two Macs on one account never collide;
    /// - the local session id, which is what "this conversation" means here;
    /// - the session's start, so that deleting `context.db` and starting over — which resets the
    ///   autoincrement to 1 — cannot make tomorrow's session id 1 look like a retry of a
    ///   conversation that is already in the account, which would silently drop it.
    ///
    /// The part suffix keeps a split session's uploads distinct while leaving each one derivable.
    static func clientSessionId(
        deviceIdHash: String, sessionId: Int64, sessionStartedAt: Double, part: Int
    ) -> String {
        let stamp = Int64(sessionStartedAt.rounded())
        let base = "context-for-claude-\(deviceIdHash)-s\(sessionId)-\(stamp)"
        return part <= 1 ? base : "\(base)-\(part)"
    }

    static func iso(_ epoch: Double) -> String {
        formatter.string(from: Date(timeIntervalSince1970: epoch))
    }

    /// Digs a retry delay out of whatever the server said. `OmiAPI` appends `retry after <value>`
    /// when the response carried a `Retry-After`; the rate limiter's own sentence reads
    /// "Try again in 42s." Both are worth honouring over a guess.
    static func retryAfterSeconds(in detail: String) -> Double? {
        for pattern in ["retry after ([0-9]+)", "in ([0-9]+) ?s"] {
            guard
                let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
                let match = regex.firstMatch(
                    in: detail, range: NSRange(detail.startIndex..., in: detail)),
                match.numberOfRanges > 1,
                let range = Range(match.range(at: 1), in: detail),
                let seconds = Double(detail[range])
            else { continue }
            return max(0, seconds)
        }
        return nil
    }

    private static nonisolated(unsafe) let formatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        // Whole seconds in UTC — the shape in the endpoint's own examples.
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()
}

// MARK: - Storage

/// Owns the uploader's handle on the database and every touch of the queue tables.
///
/// A second `ContextStore` rather than a share of the engine's: the engine keeps its writer inside
/// its own serial queue and hands it to nobody, and WAL makes a second connection cost a file handle
/// and nothing else. Both connections open with `busy_timeout = 5000`, and neither holds the writer
/// for longer than one small row — a transcript line and a queue update never wait on each other in
/// any way a person could notice.
///
/// `@unchecked Sendable` is honest for the same reason `EngineStore`'s is: every stored property is
/// touched only inside `queue`.
private final class UploadDatabase: @unchecked Sendable {
    private let queue = DispatchQueue(label: "com.omi.context-for-claude.upload", qos: .utility)
    private var store: ContextStore?

    /// Runs `body` against the queue's store, off the main thread.
    func perform<T: Sendable>(_ body: @escaping @Sendable (ContextStore) throws -> T) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            queue.async {
                do {
                    let value = try body(self.opened())
                    continuation.resume(returning: value)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    /// Opens on first use and migrates the queue tables in. Deliberately lazy: a user who never
    /// signs in should never have caused a database open on our account.
    private func opened() throws -> ContextStore {
        if let store { return store }
        let opened = try ContextStore()
        try UploadQueue.prepare(opened)
        store = opened
        ContextLog.info("Upload queue ready at \(opened.databaseURL.lastPathComponent)", "upload")
        return opened
    }
}
