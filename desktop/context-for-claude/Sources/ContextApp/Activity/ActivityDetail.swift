//
//  ActivityDetail.swift — what a row on the spine opens into, and where the words come from.
//
//  The spine is a clock: every row is one line about one minute. A row is therefore the wrong place
//  to read a conversation *in*, and until now a click on one went nowhere at all. This is the other
//  half — the thing a click opens — and it is deliberately three different screens rather than one
//  generic "record viewer", because the three rows are three different claims:
//
//  - **A conversation** is a summary standing in front of a recording, and the detail is laid out in
//    that order — the summary first, the recording behind a button. This is Omi's own conversation
//    detail (`MainWindow/Pages/ConversationDetailView.swift`) ported rather than re-invented: the
//    reader lands on the overview, the metadata chips, whatever apps made of it and the action
//    items, and reaches the transcript through `View Transcript` if they want it. It used to open
//    *on* the transcript, which was the one thing the reference deliberately tucks away — a wall of
//    speech is what a conversation was, not what it was about.
//
//    The two panes are exclusive, again as the reference has them: at this panel's height a split
//    view compresses both halves into something neither can be read in.
//  - **A memory** is already shown whole on the spine — the row never truncates it. So a detail that
//    only set the same sentence larger would be a click that bought nothing. What it adds instead is
//    *when* (the day, not just the minute) and *what was happening then*: the conversation whose
//    window contains it, which is a route from a fact back to the talk it came out of.
//  - **A task** is the same shape, plus its state.
//
//  ## The half the reference does not have
//
//  A conversation this Mac heard and never uploaded has no account behind it at all: no overview, no
//  category, no action items, nothing an app made of it. Its whole content *is* the spoken lines, so
//  hiding them behind a summary page would be an empty page with a button on it pointing at the only
//  thing there is. A local conversation therefore opens straight onto its transcript, under a
//  sentence saying why there is no summary to open first. It is the one place this screen departs
//  from the reference, and it is forced rather than chosen — the reference has no conversation the
//  account never saw.
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

/// One thing the account says somebody committed to during the conversation.
///
/// `sourceSegmentIDs` is the reference's own field and is the whole reason a summary-first screen
/// works: an item the reader does not believe is one press away from the lines it was drawn from,
/// so the transcript stays reachable *from the claim about it* rather than only from the header.
struct ActivityActionItem: Identifiable, Equatable, Sendable {
    let id: String
    let text: String
    let isCompleted: Bool
    /// The transcript segment ids the account attributed it to. Routinely empty — an older document,
    /// or an extraction that did not record where it looked.
    let sourceSegmentIDs: [String]
}

/// What one Omi app made of the conversation.
///
/// **Deliberately just the prose.** The reference draws each result under the app's icon, name and
/// author, resolved from the app catalog it keeps loaded; this app has no catalog and no way to get
/// one, and the reference's own catalog-less branch falls back to the literal word "App" — which
/// repeated down a column names nothing. So the content is shown and the identity is omitted, on the
/// same reasoning that numbers an unnamed speaker rather than inventing a name for them.
struct ActivityAppResult: Identifiable, Equatable, Sendable {
    let id: String
    let content: String
}

/// The account's own word for a conversation it has not finished with.
///
/// Only the states worth a badge are modelled: `completed` is the ordinary case and has no badge in
/// the reference either, so it is spelled `nil` here rather than as a fifth case nothing draws.
enum ActivityConversationStatus: Equatable, Sendable {
    case inProgress
    case processing
    case merging
    case failed

    /// The reference's badge text, which is the raw status with its underscores opened out.
    var label: String {
        switch self {
        case .inProgress: return "In Progress"
        case .processing: return "Processing"
        case .merging: return "Merging"
        case .failed: return "Failed"
        }
    }

    /// True while the account is still working, which is the case the summary is thin *because* of.
    var isWorking: Bool { self != .failed }
}

/// The half of a conversation that only a read can supply.
///
/// The title, the emoji, the counts and the clock all travel on the row already, so none of them are
/// here: this is exactly what the click bought, which is what makes an empty one worth saying out
/// loud rather than rendering as a shorter page.
///
/// The order of the fields is the order the reference draws them in, and that is not a coincidence —
/// it is the information architecture, written down once. Overview, then the metadata chips, then
/// what apps made of it, then the action items, and the lines last and behind a button.
struct ActivityConversationBody: Equatable, Sendable {
    var overview: String?
    /// The account's own category for the conversation, e.g. `work`. A chip in the metadata row,
    /// which is where the reference puts it too.
    var category: String?
    /// Where the account says the conversation was captured — "Desktop", "Phone", "omi". The first
    /// of the reference's three metadata chips.
    var source: String?
    /// Nil once the account has finished with it, which is the overwhelming majority of reads.
    var status: ActivityConversationStatus?
    var actionItems: [ActivityActionItem] = []
    var appResults: [ActivityAppResult] = []
    var lines: [ActivityTranscriptLine] = []

    static let empty = ActivityConversationBody()

    /// Whether the summary pane has anything on it beyond the metadata chips.
    ///
    /// Not used to hide the pane — the reference renders the chips and stops, and so does this. It
    /// is what lets the screen say *why* the page is bare when the account is still working on it,
    /// instead of leaving the reader looking at three chips and no explanation.
    var hasSummary: Bool {
        overview != nil || !actionItems.isEmpty || !appResults.isEmpty
    }
}

/// Which half of a conversation detail is on screen.
///
/// Exclusive, as the reference has them (`ConversationDetailPane`): at this panel's height a summary
/// and a transcript side by side are two columns neither of which can be read in.
enum ActivityDetailPane: Equatable, Sendable {
    case summary
    case transcript

    /// **A local conversation is always the transcript**, whatever the button says, because a
    /// conversation the account never saw has no summary half to land on — see the note at the top
    /// of this file. Everything else follows the reference exactly: summary first, transcript when
    /// it is asked for.
    static func resolve(isLocal: Bool, transcriptOpen: Bool) -> ActivityDetailPane {
        if isLocal { return .transcript }
        return transcriptOpen ? .transcript : .summary
    }
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
    /// A 401 the session could not survive. `OmiAPI` has already spent its one forced token refresh
    /// by the time this is reached, so the refusal is the account's answer and not a stale token.
    static let unauthenticated =
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

    // The summary pane, ported from the reference section by section.

    /// The bar over the card the whole summary is read off.
    static let conversationDetailsHeading = "Conversation Details"
    static let summaryHeading = "Summary"
    static let transcriptHeading = "Transcript"
    /// What an app's reading is filed under. The reference resolves the app's real name from a
    /// catalog and falls back to this when it cannot; this app has no catalog, so the fallback is
    /// the only honest label — an app wrote this, and which one is not knowable here.
    static let appResultTitle = "App"
    static let actionItemsHeading = "Action Items"
    /// The reference's own words for the section. "Insights" and not "results": what is under it is
    /// prose an app wrote about the conversation, not a status code.
    static let appInsightsHeading = "App Insights"
    /// The control that reaches the other pane, worded as the reference words it.
    static let viewTranscript = "View Transcript"
    /// …and the way back from it. The reference closes the drawer with an ✕ in its top-right corner;
    /// this panel navigates with a leading chip everywhere else, and having one screen do it the
    /// other way is a second idiom for one control's worth of benefit.
    static let backToSummary = "Summary"

    /// What an action item's transcript link is called. Two words, because they are two claims: the
    /// account recorded which lines it drew the item from, or it did not and this is just the way to
    /// the transcript.
    static let actionItemSource = "Source"
    static let actionItemTranscript = "Transcript"

    /// The account is still working, which is why the page is thin. Ported verbatim from the
    /// reference's deferred-processing block, minus its polling: this screen reads once and offers
    /// the reader the same `Try again` every other unfinished state on it offers.
    static let processing = "Processing conversation…"
    static let processingDetail = "Generating summary and action items"
    /// The account gave up on it. There is no summary coming, so the sentence does not promise one.
    static let processingFailed = "Your account couldn't finish processing this conversation."
    static let processingFailedDetail =
        "There's no summary for it. The transcript, if one was kept, is still here."

    /// A conversation the account has finished with and made nothing of. Not an error and not a
    /// wait — some conversations really are too short or too quiet to summarise.
    static let noSummary = "The account didn't write a summary for this conversation."

    /// The local half, said once at the top of the only pane a local conversation has. It answers
    /// the question the missing summary raises before the reader has to ask it.
    static let localOnly =
        "This Mac heard this conversation and never sent it to your Omi account, so nothing "
        + "summarised it. These are the lines as they were heard."
    /// What the metadata row calls a conversation that only this Mac has.
    static let localSourceLabel = "This Mac"

    /// What the memory and task details say where a conversation would be — and the caveat that
    /// keeps the section from becoming a provenance claim the record cannot support.
    static let contextHeading = "What was happening then"
    static let contextCaveat =
        "Omi doesn't record which conversation this came out of. This is the conversation that was "
        + "running at the time."
    // "Activity", not "the spine". The latter is what this code calls the chronological list among
    // itself, and it appears in no other string the user ever sees — while the back chip 40 pt above
    // this sentence says "Activity".
    static let contextNone = "Nothing else in Activity was running at that minute."
}

// MARK: - Reading the account, and this Mac

/// The production reader: the account for a conversation the account knows about, and this Mac's own
/// capture database for one only it heard.
///
/// **The credential is the signed-in session, and the route is the one the shipping clients read.**
/// `GET /v1/conversations/{id}` is authenticated by `get_current_user_uid` and returns the full
/// `Conversation` — the same call the macOS app makes to open a conversation. `OmiActivityFeed`
/// documents at length why the whole account half moved off `/v1/mcp/*`; the short version is that
/// the MCP lane is rate-limited fail-closed at 300 requests an hour, needs a second credential that
/// can be rotated out from under the app, and projects the response through strictly poorer models.
///
/// **What that buys this screen specifically**, checked against the FastAPI models rather than
/// assumed: `Conversation.transcript_segments` is a list of real `TranscriptSegment`s, and a
/// `TranscriptSegment` declares **`is_user`** — which `SimpleTranscriptSegment` did not. So an
/// account transcript can finally label the reader's own lines "You". It used to be unable to: the
/// old record did not say which voice was the user's, and guessing would have put words in their
/// mouth. The trade is `speaker_name`, which the MCP projection resolved and this model does not
/// carry — it has `speaker` (`"SPEAKER_00"`) and a `person_id` that would need its own lookup — so a
/// non-user voice is numbered rather than named.
struct ActivityConversationSource: ActivityConversationReading {

    private let isAirgapped: @Sendable () -> Bool
    private let isSignedIn: @Sendable () async -> Bool
    private let fetch: @Sendable (String) async throws -> ActivityDetailWire.FullConversation
    /// The spoken lines of a local session, or the sentence saying why there are none.
    private let local: @Sendable (Int64) async -> ActivityConversationRead

    init(
        isAirgapped: @escaping @Sendable () -> Bool = { NetworkEgress.isSuppressed(.omiAPI) },
        isSignedIn: @escaping @Sendable () async -> Bool = {
            await MainActor.run { OmiAuth.shared.isSignedIn }
        },
        fetch: @escaping @Sendable (String) async throws -> ActivityDetailWire.FullConversation = { id in
            // Percent-encoded because the id lands in the path. Conversation ids are UUIDs today,
            // which need no encoding — this is here so that the day one does not, the request is
            // still the request rather than a truncated one.
            let escaped = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
            return try await OmiAPI.shared.get(
                "v1/conversations/\(escaped)", as: ActivityDetailWire.FullConversation.self)
        },
        local: @escaping @Sendable (Int64) async -> ActivityConversationRead = {
            await ActivityConversationSource.readThisMac(session: $0)
        }
    ) {
        self.isAirgapped = isAirgapped
        self.isSignedIn = isSignedIn
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

        // One attempt. `OmiAPI` has already spent a forced token refresh on a 401 and up to three
        // jittered retries on a 429 or 5xx by the time anything throws out here, so a second ladder
        // would only multiply requests the backend has already refused.
        do {
            return .body(try await fetch(conversation.id).body())
        } catch {
            return .unread(Self.sentence(for: error))
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
            case 401: return ActivityDetailCopy.unauthenticated
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
        // Everything else on `ActivityConversationBody` stays nil and empty on purpose: there is no
        // account behind a local session, so an overview, a category, action items or an app's
        // reading of it would all have to be invented. The one field this side can honestly fill is
        // where it came from, and the answer is this machine.
        return .body(
            ActivityConversationBody(
                source: ActivityDetailCopy.localSourceLabel,
                lines: ActivityDetailWire.lines(from: hits)))
    }
}

// MARK: - The wire, and the mapping off it

/// The shapes `GET /v1/mcp/conversations/{id}` really sends, and the two mappings onto this screen.
///
/// Every field is optional and no field is a `Date`, for the reason `OmiActivityFeed`'s wire shapes
/// are written that way: this is one person's whole conversation arriving over a network, and a
/// single null must never cost the screen it was going to fill.
enum ActivityDetailWire {

    /// The parts of `Conversation` this screen draws — `structured` for the summary, and the real
    /// `transcript_segments`, which the list form of the same model omits.
    ///
    /// **Every field here is rendered by something.** `Conversation` is a large model and most of it
    /// is not this screen's business: `language`, `geolocation`, `photos`, `audio_files`,
    /// `visibility`, `starred`, `discarded`, `folder_id` and the rest are all absent because the
    /// reference's detail draws none of them either, and a decoded field with no reader is a claim
    /// the screen is silently keeping. `started_at` / `finished_at` are absent for a different
    /// reason: the row that opened this screen already carries the clock, and the header is drawn
    /// from the row before any read begins.
    struct FullConversation: Decodable, Sendable {
        let structured: Structured?
        let transcriptSegments: [Segment]?
        /// `apps_results` — what installed apps made of the conversation. The reference's
        /// "App Insights" section.
        let appsResults: [AppResult]?
        /// `ConversationSource`: which device captured it. The first metadata chip.
        let source: String?
        /// `ConversationStatus`. Absent on documents old enough to predate it, which the model
        /// itself treats as `completed`.
        let status: String?
        /// Lazy processing: stored as a raw transcript with no enrichment yet. The reference folds
        /// it in with `processing` and so does `ActivityDetailWire.status(_:deferred:)` — from the
        /// reader's side they are the same sentence, "there is no summary yet".
        let deferred: Bool?

        /// `Structured`. `emoji` is a field here and is deliberately not read: the row the reader
        /// opened already carries it, and re-reading it would let the sheet disagree with the row
        /// that opened it. `title` is omitted for the same reason. `events` is omitted because the
        /// reference's detail draws no events section at all.
        struct Structured: Decodable, Sendable {
            let overview: String?
            let category: String?
            let actionItems: [ActionItem]?
        }

        /// `ActionItem`, of which this screen reads the three fields the reference's row draws.
        ///
        /// The reference also filters on a `deleted` flag; that flag is a desktop-only field its own
        /// decoder hardcodes to `false` on every REST response, so reading it here would be reading
        /// a field the backend does not send in order to apply a filter that can never fire.
        struct ActionItem: Decodable, Sendable {
            let description: String?
            let completed: Bool?
            let sourceSegmentIds: [String]?
        }

        /// `AppResult`: `app_id` and `content`. Only the prose is carried onto the screen — see
        /// `ActivityAppResult` for why the id does not become a title.
        struct AppResult: Decodable, Sendable {
            let appId: String?
            let content: String?
        }

        /// `TranscriptSegment`: `id`, `text`, `speaker`, `speaker_id`, `is_user`, `person_id`,
        /// `start`, `end`. `speaker` is the raw `"SPEAKER_00"` label and `speaker_id` is the index
        /// the backend derives from it in `__init__`; both are read because a document written
        /// before that derivation existed can carry one without the other.
        struct Segment: Decodable, Sendable {
            let id: String?
            let text: String?
            let speaker: String?
            let speakerId: Int?
            let isUser: Bool?
            let start: Double?
        }

        func body() -> ActivityConversationBody {
            let segments = transcriptSegments ?? []
            return ActivityConversationBody(
                overview: WireText.presentable(structured?.overview),
                category: ActivityDetailWire.category(structured?.category),
                source: ActivityDetailWire.sourceLabel(source),
                status: ActivityDetailWire.status(status, deferred: deferred),
                actionItems: (structured?.actionItems ?? []).enumerated()
                    .compactMap { index, item in
                        guard let text = WireText.presentable(item.description) else { return nil }
                        return ActivityActionItem(
                            // An action item has no id of its own on the wire — the reference keys
                            // its list on the description, which collapses two identical items onto
                            // one row. The position cannot.
                            id: "action-\(index)",
                            text: text,
                            isCompleted: item.completed ?? false,
                            sourceSegmentIDs: item.sourceSegmentIds ?? [])
                    },
                appResults: (appsResults ?? []).enumerated().compactMap { index, result in
                    guard let content = WireText.presentable(result.content) else { return nil }
                    return ActivityAppResult(id: "app-result-\(index)", content: content)
                },
                lines: segments.enumerated().compactMap { index, segment in
                    guard let text = WireText.presentable(segment.text) else { return nil }
                    // `is_user` is declared non-optional on the model, so a row without it is a
                    // document older than the field. Defaulting to false is the safe half of that:
                    // an unlabelled line reads as somebody else's, never as words in the user's
                    // mouth that they did not say.
                    let isYou = segment.isUser ?? false
                    return ActivityTranscriptLine(
                        // The wire id when there is one; the position when there is not. A line with
                        // no identity of its own still has to be diffable, and two blank ids would
                        // collapse two lines onto one row.
                        id: WireText.presentable(segment.id) ?? "segment-\(index)",
                        speaker: isYou
                            ? "You"
                            : ActivityDetailWire.speaker(
                                id: segment.speakerId, rawLabel: segment.speaker),
                        isYou: isYou,
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

    /// The device a conversation was captured on, in the reference's own words for it.
    ///
    /// The one departure: `ConversationSource` has cases this table does not name, and it also has
    /// an explicit `unknown` its `_missing_` hook folds every unrecognised value into. The reference
    /// renders all of those as the chip "Unknown", which is the source chip's version of the `other`
    /// category — a chip that occupies a row to say nothing. Nil drops it instead, which is the rule
    /// the sibling mapper above already follows.
    static func sourceLabel(_ raw: String?) -> String? {
        guard let value = WireText.presentable(raw)?.lowercased() else { return nil }
        switch value {
        case "desktop": return "Desktop"
        case "omi": return "omi"
        case "phone", "phone_call": return "Phone"
        case "apple_watch": return "Apple Watch"
        case "workflow": return "Workflow"
        case "screenpipe": return "Screenpipe"
        case "friend", "friend_com": return "Friend"
        case "openglass": return "OpenGlass"
        case "frame": return "Frame"
        case "bee": return "Bee"
        case "limitless": return "Limitless"
        case "plaud": return "Plaud"
        default: return nil
        }
    }

    /// What the account is still doing with the conversation, or nil when it is done.
    ///
    /// **`deferred` and `processing` collapse into one answer**, exactly as the reference's own
    /// enrichment branch treats them (`conversation.deferred || conversation.status == .processing`).
    /// They are different mechanisms — one is lazy enrichment that has not started, the other is
    /// enrichment in flight — and they are the same sentence to the person looking at the page: the
    /// summary is not here yet.
    ///
    /// An unrecognised or absent status is `completed`, which is what the backend model itself
    /// defaults to; a badge invented for a status this code does not understand would be a badge
    /// about the client rather than about the conversation.
    static func status(_ raw: String?, deferred: Bool?) -> ActivityConversationStatus? {
        switch WireText.presentable(raw)?.lowercased() {
        case "in_progress": return .inProgress
        case "processing": return .processing
        case "merging": return .merging
        case "failed": return .failed
        default: return deferred == true ? .processing : nil
        }
    }

    /// What to call an account voice that is not the reader's own.
    ///
    /// A number, because that is all this record supports. `TranscriptSegment` carries `person_id`
    /// rather than a resolved name, and inventing a name — or borrowing one from another speaker —
    /// would attribute somebody's words to a person who may not have said them.
    ///
    /// `speaker_id` when the document has it, otherwise the index parsed out of the raw
    /// `"SPEAKER_00"` label, which is where the backend derives it from anyway.
    static func speaker(id: Int?, rawLabel: String?) -> String {
        guard let index = id ?? speakerIndex(inRawLabel: rawLabel) else { return "Speaker" }
        // One-based, because "Speaker 0" reads as a bug to everyone who is not a programmer.
        return "Speaker \(index + 1)"
    }

    /// The number out of `"SPEAKER_07"`. Nil for a label with no number in it, which is not a
    /// speaker 0 — it is a label this code does not understand, and saying "Speaker 1" for it would
    /// be a guess dressed as a fact.
    private static func speakerIndex(inRawLabel label: String?) -> Int? {
        guard let label = WireText.presentable(label) else { return nil }
        return Int(label.drop { !$0.isNumber })
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

    /// "from 9:12 AM to 9:46 AM", or "at 9:12 AM" when the conversation has no width.
    ///
    /// Words rather than an en dash, which is the reference's own phrasing
    /// (`\(date) from \(start) to \(end)`) and reads as a sentence under a headline instead of as a
    /// pair of numbers with a rule between them. The clause carries its own preposition so the
    /// caller only ever joins it to the day.
    static func window(from start: Date, duration: TimeInterval) -> String {
        guard duration >= 1 else { return "at \(time(start))" }
        return "from \(time(start)) to \(time(start.addingTimeInterval(duration)))"
    }
}
