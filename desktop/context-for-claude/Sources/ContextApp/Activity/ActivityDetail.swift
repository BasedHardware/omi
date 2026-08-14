//
//  ActivityDetail.swift — what a row on the spine opens into, and where the words come from.
//
//  The spine is a clock: every row is one line about one minute. A row is therefore the wrong place
//  to read a conversation *in*, and until now a click on one went nowhere at all. This is the other
//  half — the thing a click opens — and it is deliberately three different screens rather than one
//  generic "record viewer", because the three rows are three different claims:
//
//  - **A conversation** is a summary standing in front of a recording. The row shows the title, the
//    counts and the account's one-sentence overview; the detail is the transcript, which is the only
//    part a row can never carry. That is what makes the click worth making.
//  - **A memory** is already shown whole on the spine — the row never truncates it. So a detail that
//    only set the same sentence larger would be a click that bought nothing. What it adds instead is
//    *when* (the day, not just the minute) and *what was happening then*: the conversation whose
//    window contains it, which is a route from a fact back to the talk it came out of.
//  - **A task** is the same shape, plus its state.
//
//  ## Provenance is not invented here
//
//  `ActivityComposer` refuses to attach a memory to the conversation it falls inside, and it is
//  right: the account's seam carries no conversation id for either memories or tasks (see
//  `ActivityAccountMemory`), so an attachment drawn from a timestamp is a claim the record does not
//  support. The detail keeps that discipline — it shows the conversation that was *happening at the
//  time* and says exactly that, in those words. It never says "from".
//
//  ## Reading is a seam, and a failure is a sentence
//
//  The account is a network away and is routinely rate-limited, signed out or airgapped. Every one
//  of those is an ordinary state of this screen, never a spinner that never ends and never a blank
//  sheet: the header is built from what the *row* already knew, so a failed read costs the body and
//  nothing else, and the body says which of the failures it was in words the reader can act on.
//

import ContextCore
import Foundation

// MARK: - What was clicked

/// The three things a click on the spine can be about.
enum ActivityDetailSubject: Equatable, Sendable {
    case conversation(ActivityConversation)
    case memory(ActivityMemory)
    case task(ActivityTask)

    /// Where this thing sits on the clock — the one field all three share, and the one the
    /// surrounding context is resolved against.
    var anchor: Date {
        switch self {
        case .conversation(let conversation): return conversation.startedAt
        case .memory(let memory): return memory.timestamp
        case .task(let task): return task.timestamp
        }
    }

    /// The word over the detail. Singular, because a detail is always about one thing — the row it
    /// came from may have held a run of them.
    var overline: String {
        switch self {
        case .conversation: return "Conversation"
        case .memory: return "Memory"
        case .task: return "Task"
        }
    }
}

/// One click, resolved: what was pressed, and what the spine can say about the minute around it.
///
/// The context is captured **at the moment of the click** rather than looked up later, because the
/// stream underneath is live — days land behind the reader and the time window can move — and a
/// detail whose "what was happening then" changed while it was open would be a screen rewriting its
/// own answer.
struct ActivityDetailRequest: Equatable, Identifiable, Sendable {
    let subject: ActivityDetailSubject
    /// The conversation whose window contains this thing's instant, when one does. Always nil for a
    /// conversation: a conversation is not context for itself.
    let during: ActivityConversation?

    /// Stable across a rebuild of the stream, and prefixed by kind so a memory and a task that share
    /// an id can never collide.
    var id: String {
        switch subject {
        case .conversation(let conversation): return "conversation:\(conversation.id)"
        case .memory(let memory): return "memory:\(memory.id)"
        case .task(let task): return "task:\(task.id)"
        }
    }

    /// A conversation opens straight onto itself.
    static func conversation(_ conversation: ActivityConversation) -> ActivityDetailRequest {
        ActivityDetailRequest(subject: .conversation(conversation), during: nil)
    }

    /// Anything else opens with the minute around it resolved from the composed days.
    static func make(_ subject: ActivityDetailSubject, in days: [ActivityDay]) -> ActivityDetailRequest {
        guard case .conversation = subject else {
            return ActivityDetailRequest(
                subject: subject, during: conversation(spanning: subject.anchor, in: days))
        }
        return ActivityDetailRequest(subject: subject, during: nil)
    }

    /// The conversation whose window contains `instant`, searched over the days the stream has
    /// composed.
    ///
    /// **Closed at both ends, and the newest match wins.** Two conversations can overlap on the
    /// clock — the account's telling of one and a local session that started while it ran — and the
    /// composer already prefers the account's, which is the later of the two to start whenever they
    /// really are the same talk. A zero-length conversation contains only its own instant, which is
    /// the honest reading of a window with no width.
    static func conversation(spanning instant: Date, in days: [ActivityDay]) -> ActivityConversation? {
        var best: ActivityConversation?
        for day in days {
            for row in day.rows {
                guard case .conversation(let conversation) = row.content else { continue }
                guard conversation.startedAt <= instant, instant <= conversation.finishedAt else {
                    continue
                }
                if let current = best, current.startedAt >= conversation.startedAt { continue }
                best = conversation
            }
        }
        return best
    }
}

// MARK: - A conversation, in full

/// One line of a transcript, as a detail screen shows it.
///
/// `offset` and not a wall-clock time: a transcript is read as a recording — "four minutes in" —
/// and the wall clock is already stated once, in the header, for the conversation as a whole.
struct ActivityTranscriptLine: Identifiable, Equatable, Sendable {
    let id: String
    /// What to call the voice. Never "You" unless the record actually says so — see
    /// `ActivityDetailWire.speaker(label:)`.
    let speaker: String
    /// True only for a line this Mac heard through the microphone as the user's own speech.
    let isYou: Bool
    let text: String
    /// Seconds from the start of the conversation.
    let offset: TimeInterval
}

/// The half of a conversation that only a read can supply.
///
/// The title, the emoji, the counts and the clock all travel on the row already, so none of them are
/// here: this is exactly what the click bought, which is what makes an empty one worth saying out
/// loud rather than rendering as a shorter page.
struct ActivityConversationBody: Equatable, Sendable {
    var overview: String?
    /// The account's own category for the conversation, e.g. `work`. Shown as a chip beside the
    /// timing, which is where the reference puts it too.
    var category: String?
    var lines: [ActivityTranscriptLine] = []

    static let empty = ActivityConversationBody()
}

/// What one read of a conversation came back with. **Never a throw**, for the reason
/// `ActivityAccountReading` never throws: an unread conversation is an ordinary state of this
/// screen, and the sentence explaining it is the screen's content rather than an error to handle.
enum ActivityConversationRead: Equatable, Sendable {
    case body(ActivityConversationBody)
    case unread(String)
}

/// One conversation, read in full.
protocol ActivityConversationReading: Sendable {
    func read(_ conversation: ActivityConversation) async -> ActivityConversationRead
}

/// The reader for previews, the render harness, and every test that is about presentation rather
/// than about the network.
struct ActivityConversationUnavailable: ActivityConversationReading {
    let sentence: String

    init(sentence: String = ActivityDetailCopy.noReader) {
        self.sentence = sentence
    }

    func read(_ conversation: ActivityConversation) async -> ActivityConversationRead {
        .unread(sentence)
    }
}

// MARK: - Everything this screen says when it cannot show a transcript

/// Every failure sentence in one place, so the phrasing is a test rather than a screenshot — and so
/// that "I couldn't read it" is never the answer to a question the reader could have acted on.
///
/// The distinctions are the point. Being rate-limited is a *wait*; being signed out is a *sign in*;
/// a rejected key is a *reconnect*; Airgap Mode is a switch the user turned on themselves. Telling
/// all four "I couldn't reach your account" is true and useless.
enum ActivityDetailCopy {
    static let airgapped =
        "Airgap Mode is on, so this conversation isn't being read from your account. Turn it off in "
        + "Settings to see the transcript."
    static let signedOut = "Sign in to Omi to read this conversation."
    static let noKey =
        "Omi couldn't authenticate this Mac, so this conversation can't be read. Sign out and back "
        + "in from the menu bar to reconnect it."
    static let rateLimited =
        "Your Omi account is rate-limiting this Mac right now. Wait a moment and try again."
    static let gone = "This conversation is no longer in your account."
    static let locked = "A paid plan is required to open this conversation."
    static let noAnswer = "I couldn't reach your Omi account to read this conversation."
    static let unreadable = "Your account answered with something I couldn't read."
    /// A local session whose transcript is in a database this app has not opened yet.
    static let captureClosed =
        "This Mac's capture isn't open yet, so the spoken lines can't be read. Try again in a moment."
    static let captureFailed =
        "I couldn't read this Mac's capture just now, so this is not an empty transcript — try again."
    /// The stand-in reader: a surface built without one, which is every preview and every frame the
    /// render harness draws.
    static let noReader = "This surface was built without a way to read the account."

    /// The two lines a conversation with nothing in it shows. Not a failure — a great many account
    /// conversations really do arrive with a summary and no segments.
    static let noTranscript = "No transcript was kept for this conversation."
    static let noTranscriptDetail =
        "The account kept a summary of it. What was said was not stored."
    /// A local session that the database has no lines for, which is a different claim again: this
    /// Mac heard it and wrote nothing down.
    static let noLocalTranscript = "This Mac didn't keep any lines from this conversation."

    /// What the memory and task details say where a conversation would be — and the caveat that
    /// keeps the section from becoming a provenance claim the record cannot support.
    static let contextHeading = "What was happening then"
    static let contextCaveat =
        "Omi doesn't record which conversation this came out of. This is the conversation that was "
        + "running at the time."
    static let contextNone = "Nothing else on the spine was running at that minute."
}

// MARK: - Reading the account, and this Mac

/// The production reader: the account for a conversation the account knows about, and this Mac's own
/// capture database for one only it heard.
///
/// **The credential is the `omi_mcp_…` key, not the signed-in session's token.** Every route in
/// `backend/routers/mcp.py` — including `GET /v1/mcp/conversations/{id}` — depends on
/// `get_uid_from_mcp_api_key`, which looks the bearer up in `mcp_api_keys` after an explicit
/// `startswith("omi_mcp_")`. A Firebase ID token is not found there and comes back `401`. This is the
/// same path `OmiActivityFeed` reads the spine with, through the same `OmiMCPRead` helper, and a
/// rejected key buys exactly one re-provision and one retry for the same reason it does there.
///
/// **What the endpoint actually gives us**, checked against the FastAPI response model rather than
/// assumed: `FullConversation` is `SimpleConversation` plus `transcript_segments`, and
/// `SimpleStructured` is `title`, `overview`, `category` — **there is no `emoji` on this route
/// either**. So the emoji on this screen is the one the row already carried, and what the read adds
/// is the category and the segments. `SimpleTranscriptSegment` carries `speaker_id`/`speaker_name`
/// and **no `is_user` flag**, which is why an account transcript never labels a line "You": the
/// record does not say which voice was the user's, and guessing would put words in their mouth.
struct ActivityConversationSource: ActivityConversationReading {

    private let isAirgapped: @Sendable () -> Bool
    private let isSignedIn: @Sendable () async -> Bool
    /// The bearer for the next attempt — `nil` asks for the current key, a rejected key asks for its
    /// replacement. Same contract as `OmiActivityFeed`'s.
    private let credential: @Sendable (String?) async -> String?
    private let fetch: @Sendable (String, String) async throws -> ActivityDetailWire.FullConversation
    /// The spoken lines of a local session, or the sentence saying why there are none.
    private let local: @Sendable (Int64) async -> ActivityConversationRead

    init(
        isAirgapped: @escaping @Sendable () -> Bool = { NetworkEgress.isSuppressed(.omiAPI) },
        isSignedIn: @escaping @Sendable () async -> Bool = {
            await MainActor.run { OmiAuth.shared.isSignedIn }
        },
        credential: @escaping @Sendable (String?) async -> String? = { rejected in
            guard let rejected else { return await MCPKeyProvisioner.shared.key() }
            return await MCPKeyProvisioner.shared.key(replacing: rejected)
        },
        fetch: @escaping @Sendable (String, String) async throws -> ActivityDetailWire.FullConversation = {
            id, key in
            try await OmiMCPRead.get(
                "v1/mcp/conversations/\(id)", key: key, query: [:],
                as: ActivityDetailWire.FullConversation.self)
        },
        local: @escaping @Sendable (Int64) async -> ActivityConversationRead = {
            await ActivityConversationSource.readThisMac(session: $0)
        }
    ) {
        self.isAirgapped = isAirgapped
        self.isSignedIn = isSignedIn
        self.credential = credential
        self.fetch = fetch
        self.local = local
    }

    private static let category = "activity"

    func read(_ conversation: ActivityConversation) async -> ActivityConversationRead {
        switch conversation.source {
        case .local:
            guard let sessionID = ActivityDetailWire.localSession(conversation.id) else {
                return .unread(ActivityDetailCopy.gone)
            }
            return await local(sessionID)
        case .account:
            return await readAccount(conversation)
        }
    }

    // MARK: The account

    private func readAccount(_ conversation: ActivityConversation) async -> ActivityConversationRead {
        // Answered before a URL exists, for the reason `OmiActivityFeed` answers them there: a
        // switch only the user can flip must not cost a network refusal and a suppression record.
        guard !isAirgapped() else {
            NetworkEgress.recordSuppression(.omiAPI, outcome: .degraded)
            return .unread(ActivityDetailCopy.airgapped)
        }
        guard await isSignedIn() else { return .unread(ActivityDetailCopy.signedOut) }
        guard let key = await credential(nil) else {
            ContextLog.error("No Omi MCP key for this Mac; a conversation cannot be read", Self.category)
            return .unread(ActivityDetailCopy.noKey)
        }

        do {
            return .body(try await fetch(conversation.id, key).body())
        } catch {
            guard case .http(401, _)? = error as? OmiAPIError else {
                return .unread(Self.sentence(for: error))
            }
            // One re-provision and one retry, exactly as the spine's own read spends: a key the
            // account has just issued and immediately refused is the account's answer.
            guard let replacement = await credential(key), replacement != key else {
                return .unread(ActivityDetailCopy.noKey)
            }
            do {
                return .body(try await fetch(conversation.id, replacement).body())
            } catch {
                return .unread(Self.sentence(for: error))
            }
        }
    }

    /// The sentence a failure renders as. Deliberately mapped from the *status*, never from the
    /// server's own `detail` string — a FastAPI detail can quote the request back, and the request
    /// carries a conversation id.
    static func sentence(for error: Error) -> String {
        guard let apiError = error as? OmiAPIError else { return ActivityDetailCopy.noAnswer }
        switch apiError {
        case .airgapMode: return ActivityDetailCopy.airgapped
        case .notSignedIn: return ActivityDetailCopy.signedOut
        case .decoding: return ActivityDetailCopy.unreadable
        case .transport: return ActivityDetailCopy.noAnswer
        case .http(let status, _):
            switch status {
            case 401: return ActivityDetailCopy.noKey
            case 402: return ActivityDetailCopy.locked
            case 404: return ActivityDetailCopy.gone
            case 429: return ActivityDetailCopy.rateLimited
            default: return ActivityDetailCopy.noAnswer
            }
        }
    }

    // MARK: This Mac

    /// One local session's spoken lines.
    ///
    /// The store is asked for on the main actor and read on a detached task, the same bargain
    /// `ActivityStore` strikes: the provider is only meaningful where the engine lives, and a
    /// synchronous database read does not belong on the thread drawing the panel.
    static func readThisMac(session id: Int64) async -> ActivityConversationRead {
        guard let store = await MainActor.run(body: { Engine.shared.contextStore }) else {
            return .unread(ActivityDetailCopy.captureClosed)
        }
        let hits: [Hit]
        do {
            hits = try await Task.detached(priority: .userInitiated) {
                try Queries.transcript(store, sessionId: id)
            }.value
        } catch {
            // The error itself is deliberately not carried into the sentence: a GRDB error renders
            // its failing statement and its bound arguments.
            ContextLog.error("Could not read a local transcript", category)
            return .unread(ActivityDetailCopy.captureFailed)
        }
        return .body(ActivityConversationBody(lines: ActivityDetailWire.lines(from: hits)))
    }
}

// MARK: - The wire, and the mapping off it

/// The shapes `GET /v1/mcp/conversations/{id}` really sends, and the two mappings onto this screen.
///
/// Every field is optional and no field is a `Date`, for the reason `OmiActivityFeed`'s wire shapes
/// are written that way: this is one person's whole conversation arriving over a network, and a
/// single null must never cost the screen it was going to fill.
enum ActivityDetailWire {

    /// `FullConversation` = `SimpleConversation` + `transcript_segments`.
    struct FullConversation: Decodable, Sendable {
        let structured: Structured?
        let transcriptSegments: [Segment]?

        /// `SimpleStructured`: `title`, `overview`, `category`. No `emoji` — see the note on
        /// `ActivityConversationSource`.
        struct Structured: Decodable, Sendable {
            let overview: String?
            let category: String?
        }

        /// `SimpleTranscriptSegment`: `id`, `text`, `speaker_id`, `speaker_name`, `start`, `end`.
        struct Segment: Decodable, Sendable {
            let id: String?
            let text: String?
            let speakerId: Int?
            let speakerName: String?
            let start: Double?
        }

        func body() -> ActivityConversationBody {
            let segments = transcriptSegments ?? []
            return ActivityConversationBody(
                overview: WireText.presentable(structured?.overview),
                category: ActivityDetailWire.category(structured?.category),
                lines: segments.enumerated().compactMap { index, segment in
                    guard let text = WireText.presentable(segment.text) else { return nil }
                    return ActivityTranscriptLine(
                        // The wire id when there is one; the position when there is not. A line with
                        // no identity of its own still has to be diffable, and two blank ids would
                        // collapse two lines onto one row.
                        id: WireText.presentable(segment.id) ?? "segment-\(index)",
                        speaker: ActivityDetailWire.speaker(
                            named: segment.speakerName, id: segment.speakerId),
                        // The account's transcript carries no `is_user`, so no line off it is ever
                        // claimed as the reader's own voice.
                        isYou: false,
                        text: text,
                        offset: max(0, segment.start ?? 0))
                })
        }
    }

    /// `other` is the backend's own "we didn't work one out", and a chip that says so is a chip
    /// saying nothing — the reference drops it for exactly that reason.
    static func category(_ raw: String?) -> String? {
        guard let trimmed = WireText.presentable(raw), trimmed.lowercased() != "other" else {
            return nil
        }
        return trimmed
    }

    /// What to call an account voice: the name the account resolved, or its diarization index, and
    /// never "You".
    static func speaker(named name: String?, id: Int?) -> String {
        if let named = WireText.presentable(name) { return named }
        guard let id else { return "Speaker" }
        // One-based, because "Speaker 0" reads as a bug to everyone who is not a programmer.
        return "Speaker \(id + 1)"
    }

    /// What to call a voice this Mac heard for itself.
    ///
    /// `Hit.kind` is the app's own vocabulary and it is exactly two claims wide — `said` is the user
    /// and `heard` is somebody else — so the label never has to be invented. `speakerLabel` refines
    /// the second half where diarization ran: two `heard` lines with different labels are two people,
    /// which `kind` alone cannot express.
    static func speaker(label: String?) -> String {
        guard let label = WireText.presentable(label) else { return "Someone else" }
        let digits = label.drop { !$0.isNumber }
        guard let index = Int(digits) else { return label }
        return "Speaker \(index + 1)"
    }

    /// A local session's lines, in the order they were spoken.
    static func lines(from hits: [Hit]) -> [ActivityTranscriptLine] {
        guard let first = hits.first else { return [] }
        return hits.enumerated().compactMap { index, hit in
            guard let text = WireText.presentable(hit.text) else { return nil }
            let isYou = hit.kind == "said"
            return ActivityTranscriptLine(
                id: "line-\(index)",
                speaker: isYou ? "You" : speaker(label: hit.speakerLabel),
                isYou: isYou,
                text: text,
                offset: max(0, hit.at - first.at))
        }
    }

    /// The session id inside a local conversation's composite id, or nil for an account one. See
    /// `ActivityConversation.localID`.
    static func localSession(_ id: String) -> Int64? {
        let prefix = "local:"
        guard id.hasPrefix(prefix) else { return nil }
        return Int64(id.dropFirst(prefix.count))
    }
}

// MARK: - The model

/// The body of a conversation detail, and the one place it is read.
///
/// A `@MainActor` object rather than a `.task` inside the view, for the reason `ActivityStore` is
/// one: a view that reads the network in its own body cannot be rendered in a test or a preview, and
/// a retry has to be able to re-run the read without re-mounting the screen it is on.
@MainActor
final class ActivityDetailModel: ObservableObject {

    enum State: Equatable {
        /// The read is running. The header is already on screen throughout — this is only ever the
        /// state of the body.
        case reading
        case read(ActivityConversationBody)
        /// Why there is nothing to show, in words the reader can act on.
        case unread(String)
    }

    @Published private(set) var state: State = .reading

    private let source: ActivityConversationReading
    /// The read in flight, so a second open cancels the first rather than racing it onto the screen.
    private var inFlight: Task<Void, Never>?
    /// What `retry()` runs again.
    private var subject: ActivityConversation?

    init(source: ActivityConversationReading = ActivityConversationSource()) {
        self.source = source
    }

    /// A model with its answer already in it, for previews, the render harness and the composition
    /// tests. Nothing it holds can reach the network.
    init(state: State) {
        self.source = ActivityConversationUnavailable()
        self.state = state
    }

    deinit { inFlight?.cancel() }

    func read(_ conversation: ActivityConversation) {
        subject = conversation
        inFlight?.cancel()
        state = .reading
        let source = self.source
        inFlight = Task { [weak self] in
            let answer = await source.read(conversation)
            guard !Task.isCancelled else { return }
            self?.absorb(answer)
        }
    }

    func retry() {
        guard let subject else { return }
        read(subject)
    }

    private func absorb(_ answer: ActivityConversationRead) {
        switch answer {
        case .body(let body): state = .read(body)
        case .unread(let sentence): state = .unread(sentence)
        }
    }
}

// MARK: - Escape, when a detail is showing

/// Where "go back to the spine" lives, so that Escape can find it.
///
/// **This exists because the panel takes Escape before anything in the view hierarchy can.**
/// `SearchPanel.sendEvent` intercepts key code 53 and calls `SearchBarWindow.dismiss()` without
/// calling `super`, which is correct for a Spotlight overlay with one body — and wrong the moment
/// the panel has somewhere to go *back* to. The field's own `cancelOperation:` never runs for
/// Escape while that interception stands, and a local `NSEvent` monitor never sees these events at
/// all for a non-activating panel (measured; see the note on `sendEvent`).
///
/// So the surface leaves a way back here while a detail is on screen, and Escape asks for it before
/// it closes the window. A `@MainActor` singleton rather than a closure threaded down from the
/// window, because the window's key handling happens in an `NSPanel` subclass that holds no
/// reference to the view at all.
@MainActor
final class ActivityDetailEscape {
    static let shared = ActivityDetailEscape()

    private var back: (() -> Void)?

    /// Whether a detail is currently showing — which is exactly the question "does Escape mean back".
    var isShowing: Bool { back != nil }

    /// Called by the surface when it pushes a detail. Replacing an existing hold is ordinary: a
    /// memory detail can open the conversation that was running at the time.
    func hold(_ back: @escaping () -> Void) { self.back = back }

    /// Called when the detail goes away by any other route — the back control, or the surface
    /// leaving the screen entirely.
    func release() { back = nil }

    /// Escape. **True means it was consumed** — a detail was showing and the surface has been taken
    /// back to the spine — and the panel must then stay up. False means there was nothing to go back
    /// to and Escape has its ordinary meaning.
    @discardableResult
    func consume() -> Bool {
        guard let back else { return false }
        // Cleared before the callback runs, so a handler that throws the surface away cannot leave a
        // stale route behind it.
        self.back = nil
        back()
        return true
    }
}

// MARK: - Formatting

extension ActivityFormat {
    /// "Wednesday 6 August at 11:20 AM" — the day *and* the minute, which is the thing the spine's
    /// own gutter cannot say: a row prints the time and leaves the day to the header above it, and a
    /// detail has no header above it.
    static func stamp(_ date: Date, calendar: Calendar = .current, now: Date = Date()) -> String {
        "\(day(date, calendar: calendar, now: now)) at \(time(date))"
    }

    /// "4:07" — how far into a recording a line was said. Always at least `m:ss`, and hours only
    /// when there are any.
    static func offset(_ seconds: TimeInterval) -> String {
        let total = Int(max(0, seconds).rounded())
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let secs = total % 60
        if hours > 0 { return String(format: "%d:%02d:%02d", hours, minutes, secs) }
        return String(format: "%d:%02d", minutes, secs)
    }

    /// "9:12 AM – 9:46 AM", or just the start when the conversation has no width. The dash is an en
    /// dash: it is a range, not a hyphenation.
    static func window(from start: Date, duration: TimeInterval) -> String {
        guard duration >= 1 else { return time(start) }
        return "\(time(start)) – \(time(start.addingTimeInterval(duration)))"
    }
}
