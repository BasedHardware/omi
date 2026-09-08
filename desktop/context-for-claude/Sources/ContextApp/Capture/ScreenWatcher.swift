import ContextCore
import AppKit
import CoreGraphics
import CoreImage
import Foundation
import ImageIO
import ScreenCaptureKit
import Vision

/// Identity for the immutable ScreenCaptureKit objects associated with one shareable-content
/// snapshot. A new snapshot may contain the same window ID with new geometry or ownership, so object
/// identity and the current frame are part of the key rather than relying on the numeric ID alone.
struct CaptureRequestKey: Equatable {
    let windowID: CGWindowID
    let windowIdentity: ObjectIdentifier
    let windowFrame: CGRect

    init(window: SCWindow) {
        windowID = window.windowID
        windowIdentity = ObjectIdentifier(window)
        windowFrame = window.frame
    }

    init(windowID: CGWindowID, windowIdentity: ObjectIdentifier, windowFrame: CGRect = .zero) {
        self.windowID = windowID
        self.windowIdentity = windowIdentity
        self.windowFrame = windowFrame
    }
}

private struct CachedCapture {
    let key: CaptureRequestKey
    let filter: SCContentFilter
    let configuration: SCStreamConfiguration
}

/// Samples the active window on a timer, reads it with Vision when the pixels actually changed, and
/// hands every worthwhile observation to `onFrame`.
///
/// Two costs shape this class, because it runs for the whole life of the machine: enumerating
/// windows through the WindowServer, and Vision OCR. The first is amortised behind a cached
/// `SCShareableContent` snapshot; the second is gated on a perceptual hash of the capture, so a
/// screen nobody is touching costs one small screenshot and nothing else.
///
/// Three rules decide what a tick is allowed to produce, and all three exist because a frame here is
/// permanent, searchable, and quoted back to a model:
///
/// - **Nothing sensitive is read.** `Redaction.isSensitiveWindow` refuses the window outright, and
///   `Redaction.scrub` runs on the title and on the OCR result before either can be handed on.
/// - **Nothing of ours is read.** This app's own window, Claude Desktop, and terminals running
///   Claude Code are skipped, so the assistant's output cannot be recycled into its own memory.
/// - **Nothing empty is stored.** Recent screens are remembered as a ring, and a frame with almost
///   no text in a window that is already the newest row is dropped rather than written.
///
/// Against those three sits one rule pushing the other way, because a gate with no ceiling starves:
/// **nothing is silently forgotten.** The hash gate answers "is this a screen we have seen", and for
/// a window nobody is touching the answer is yes for as long as the user keeps looking at it — so
/// reading one document for an hour produced no rows at all, and sitting still in front of a
/// document is what reading looks like. A capture suppressed for
/// ``ScreenPipeline/forceCaptureInterval`` is stored regardless of how similar it looks.
@MainActor
final class ScreenWatcher {

    /// Called on the main actor for each frame worth storing. Ticks that change nothing call nothing.
    var onFrame: ((Frame) -> Void)?

    /// The subtrees of a captured accessibility tree, handed over *before* the frame that references
    /// them. Separate from `onFrame` because they are deduplicated against every earlier frame: most
    /// ticks contribute a handful of new rows to a table that already holds the rest of the window.
    var onAXNodes: (([AXNodeRecord]) -> Void)?

    /// Why screen capture is standing down, or nil the moment it is not.
    ///
    /// Called only on a change, and it is the only route from this loop to anything a person can
    /// see. "Pause on Inactivity" used to stand capture down with nothing but a log line, so the
    /// menu bar went on saying the app was capturing and the heartbeat file went on reporting a
    /// healthy pipeline while nothing at all was being recorded — a recorder that lies about
    /// recording is worse than one that admits it stopped.
    ///
    /// It carries a ``ScreenStandDown`` rather than a sentence because the engine has to *act*
    /// differently on the three of them and a string cannot be branched on. That was the second
    /// half of the 2 August defect: the grant vanished mid-life, the tick started refusing itself
    /// on every pass, and there was no shape in this channel that could say "this is not a pause,
    /// this needs the user" — so it said nothing at all and idled for twenty-nine hours.
    var onStandDown: (@MainActor (ScreenStandDown?) -> Void)?

    /// How the stored picture reaches disk.
    ///
    /// A property rather than a call so that the *ordering* is testable: what matters about an
    /// excluded window is not that its screenshot was deleted afterwards but that its bytes were
    /// never produced, and nothing can observe that from the filesystem afterwards.
    var writeImage: @MainActor (Data, Double) -> String? = { data, capturedAt in
        ScreenPipeline.writeFrameImage(data, capturedAt: capturedAt)
    }

    /// The gate this watcher answers to. Injected so a test drives a real engine over a temporary
    /// configuration rather than the process-wide one holding the user's own exclusions.
    private let exclusions: ExclusionEngine

    init(exclusions: ExclusionEngine = .shared) {
        self.exclusions = exclusions
    }

    // MARK: - Lifecycle

    private var loop: Task<Void, Never>?

    var isRunning: Bool { loop != nil }

    /// How long to wait before the next tick, given how long this one took.
    ///
    /// **The interval is a cadence, not a cooldown.** This loop used to sleep the full period *after*
    /// the work, which quietly made the real cadence `interval + work` — and the work is not uniform:
    /// a tick the dedup gate suppresses costs a capture and a hash, while a tick that stores costs
    /// OCR, an accessibility walk and a HEIC encode on top. So the pipeline slowed down precisely on
    /// the ticks that were producing something. Measured on this machine's own database, consecutive
    /// stored frames averaged **3.79 s apart against a configured 3.0 s** — a 26% rate loss that no
    /// setting asked for and nothing reported, and about two thirds of the measured shortfall against
    /// the shipping app's Rewind capture, whose timer is 3 s of wall clock regardless of what its
    /// indexer is doing.
    ///
    /// Sleeping only the remainder restores the promise. It cannot spin: when a tick outruns the
    /// period this returns zero and the next tick starts at once, and a tick that took longer than
    /// the period is by definition doing real work rather than looping. A backwards clock (NTP
    /// correction, wake from sleep) makes `elapsed` negative and falls back to the whole period —
    /// pausing rather than hammering the WindowServer is the safe direction for nonsense input.
    ///
    /// Pure and `nonisolated` so the cadence is assertable without a display, a WindowServer or a
    /// three-second wait.
    nonisolated static func sleepAfterTick(period: TimeInterval, elapsed: TimeInterval) -> TimeInterval {
        guard elapsed.isFinite, elapsed > 0 else { return period }
        return max(0, period - elapsed)
    }

    func start(interval: TimeInterval = 3.0) {
        guard loop == nil else { return }
        let period = max(0.5, interval)

        // The watchdog clock starts now rather than at nil, so a watcher whose first few ticks land
        // during a login-item launch — window server still coming up, no frontmost application yet —
        // gets its full patience before anything is called stalled.
        lastServedAt = ContextTime.now

        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                let startedAt = ContextTime.now
                await self.tick()
                let sleep = Self.sleepAfterTick(
                    period: period, elapsed: ContextTime.now - startedAt)
                guard sleep > 0 else { continue }
                try? await Task.sleep(nanoseconds: UInt64(sleep * 1_000_000_000))
            }
        }
        ContextLog.info("Screen watcher started (every \(period)s)", "screen")
    }

    func stop() {
        // Deliberately not guarded on there being a loop to cancel. "Stopped" is a statement about
        // what may still be handed over, not about a task handle, and the tick that matters here is
        // one already suspended somewhere in the middle of itself.
        loop?.cancel()
        let wasRunning = loop != nil
        loop = nil
        // A last, truthful word before the hand-overs go: whatever this watcher was holding capture
        // down for, it is not holding it down any more — the owner is about to say why capture
        // stopped, and a stale "no activity for 5 minutes" underneath that would contradict it.
        reportStandDown(nil)
        // Cancelling a task does not resume an `await` that is already suspended, so a tick sitting
        // in OCR or in an accessibility walk still runs to completion after this returns — that is
        // seconds of work, and it used to end in a write. Clearing *every* hand-over here is what
        // makes "stopped" mean stopped: the frame is dropped, its image is never written, and the
        // accessibility rows it would have referenced are never stored. Those rows are why this is
        // not the caller's business to remember — nothing points at them, so nothing prunes them,
        // and one forgotten `= nil` left a window's full text in the database after the user had
        // switched screen capture off.
        onFrame = nil
        onAXNodes = nil
        onStandDown = nil
        // Resuming should always produce one full observation: whatever is on screen after a pause
        // is new information regardless of what was there before.
        recentHashes.removeAll()
        lastAppName = nil
        lastWindowTitle = nil
        lastFullPassAt = nil
        lastSkipReason = nil
        census.reset()
        cachedContent = nil
        cachedContentAt = nil
        cachedCapture = nil
        lastServedAt = nil
        if wasRunning { ContextLog.info("Screen watcher stopped", "screen") }
    }

    // MARK: - State carried between ticks

    /// Perceptual hashes of the last few *distinct* screens — the whole idle-cost story.
    ///
    /// A ring rather than a single previous hash because the frames that actually repeat do not
    /// repeat consecutively: a terminal spinner alternates between two or three renderings, a
    /// progress bar oscillates, a caret blinks against a changing clock. Compared only against its
    /// immediate predecessor every one of those looks like new content forever, which is where the
    /// bulk of the near-empty rows in the database came from.
    private var recentHashes: [UInt64] = []
    /// What the last *emitted* frame said, so a title-only change is still recorded.
    private var lastAppName: String?
    private var lastWindowTitle: String?

    /// When the OCR pipeline last ran, forced or not — the clock behind
    /// ``ScreenPipeline/forceCaptureInterval``. Nil until the first pass of a run.
    ///
    /// Deliberately "last full pass" rather than "last row written". The only pass that writes
    /// nothing is one the low-signal drop refused, and that only happens when the window already
    /// owns the newest row, so nothing is lost by counting it — whereas measuring from the last
    /// *row* would let a text-free window re-run OCR on every single tick forever.
    private var lastFullPassAt: Double?

    private var cachedContent: SCShareableContent?
    private var cachedContentAt: Date?

    /// The one-shot screenshot API creates its capture machinery around the filter and
    /// configuration it receives. Keep those request objects alive while the exact same window
    /// snapshot remains active; a changed `SCWindow` identity gets a fresh filter so a refreshed
    /// `SCShareableContent` snapshot can never inherit stale geometry or ownership.
    private var cachedCapture: CachedCapture?

    private var lastSkipReason: String?
    private var lastErrorLoggedAt: Date?
    /// What the last few hundred ticks concluded. See ``CaptureCensus``.
    private var census = CaptureCensus()
    /// The last value handed to ``onStandDown``, so a steady state is announced once.
    private var standDown: ScreenStandDown?

    /// **When the WindowServer last proved it is still answering this process.**
    ///
    /// The clock behind ``stallReason(lastServedAt:now:threshold:)``, and what it measures is
    /// deliberately narrow: *unexplained* silence. A tick that ends because the user is looking at
    /// an excluded app, at Claude's own output, or at Mission Control never reaches the WindowServer
    /// at all — that is the app declining to record, not the OS declining to answer — so those ticks
    /// reset it. What does not reset it is `SCShareableContent` throwing, a frontmost application
    /// with no window the snapshot can see, and a capture that fails: the three signatures of a
    /// window-server connection whose capture rights have gone stale.
    private var lastServedAt: Double?

    /// How long the WindowServer may go on refusing before the app stops calling the screen half
    /// healthy.
    ///
    /// Three minutes — sixty consecutive refused ticks at the 3 s cadence. Long enough that a wake
    /// from sleep, a display reconfiguration or a fast user switch settles inside it; short enough
    /// that a user who walks away for a coffee comes back to an app that has already said something.
    /// The alternative that shipped is *never*, which cost twenty-nine hours.
    ///
    /// `nonisolated` so the threshold and the decision it feeds can both be read without the main
    /// actor — the same reason `PermissionRun.leadIn` is.
    nonisolated static let stallSeconds: Double = 180

    /// Whether the screen half has been silent long enough to say so, and what to say.
    ///
    /// Pure and separate from the tick for the same reason ``idlePauseReason(pausesOnInactivity:isIdle:)``
    /// is: this is a promise about a threshold, and a promise has to be assertable without a
    /// WindowServer, a display, or a granted TCC record.
    nonisolated static func stallReason(
        lastServedAt: Double?,
        now: Double,
        threshold: Double = stallSeconds
    ) -> String? {
        guard let lastServedAt else { return nil }
        let elapsed = now - lastServedAt
        // A backwards clock (NTP correction, wake from sleep) is not evidence of a stall. Failing
        // towards "still healthy" is right here: the next tick that genuinely fails re-arms this
        // against a sane `now`, and a false alarm on the one surface the user trusts is expensive.
        guard elapsed.isFinite, elapsed >= threshold else { return nil }
        let minutes = Int((elapsed / 60).rounded(.down))
        let howLong = minutes >= 1 ? "\(minutes) minute\(minutes == 1 ? "" : "s")" : "a while"
        return "Screen capture has produced nothing for \(howLong) — macOS is refusing this app's "
            + "screen requests. Reopening Context for Claude usually fixes it."
    }

    // MARK: - One tick

    private func tick() async {
        let outcome = await tickOutcome()
        // One line per few hundred ticks, not per tick. See ``CaptureCensus``.
        if let line = census.record(outcome) { ContextLog.info(line, "screen") }
    }

    /// One pass of the loop, and what it concluded. Every path returns exactly one ``TickOutcome``
    /// so the census can account for the whole cadence rather than only for the frames that survived
    /// it — the distinction between "not firing often enough" and "firing and discarding" is the one
    /// this pipeline could not previously make about itself.
    private func tickOutcome() async -> TickOutcome {
        guard !Task.isCancelled else { return .standDown }
        // First, because it is the only guard whose answer can change without anything on this Mac
        // moving: a grant is dropped by the OS, not by the user's hands. It used to be a bare
        // `hasPermission()` that logged once and idled — the exact shape of the twenty-nine-hour
        // failure — and it now reaches the engine as something the engine can act on.
        if let block = Permissions.screenBlock() {
            reportStandDown(.blocked(block))
            noteServed()
            return .standDown
        }
        guard !ScreenPipeline.isScreenLocked() else {
            reportStandDown(.paused("Screen locked"))
            noteSkip("screen locked")
            noteServed()
            return .standDown
        }
        // Settings > Capture > "Pause on Inactivity", which until now was a switch wired to nothing.
        // Read live rather than cached: the answer is a system counter, and caching it is how a
        // paused recorder stays paused after the user comes back.
        //
        // Reported before it is acted on, and cleared on the first tick that is *not* idle, so the
        // sentence in the menu bar and in the heartbeat file tracks the gate rather than lagging a
        // tick behind it. A returning user sees live capture on their next tick, not on their next
        // frame — those are not the same moment when the screen has not changed.
        let idlePause = Self.idlePauseReason(
            pausesOnInactivity: SettingsStore.shared.pausesOnInactivity,
            isIdle: CaptureActivity.isIdle())
        if let idlePause {
            reportStandDown(.paused(idlePause))
            noteSkip(idlePause)
            noteServed()
            return .standDown
        }
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            noteSkip("no frontmost application")
            // Nothing on screen to capture is not the WindowServer refusing us.
            noteServed()
            return .standDown
        }

        let bundleID = frontApp.bundleIdentifier ?? ""
        let appName = frontApp.localizedName ?? (bundleID.isEmpty ? "Unknown" : bundleID)

        // Mission Control, App Exposé, Launchpad and Dock menus all make the Dock frontmost, and
        // none of them is a surface the user is reading.
        guard bundleID != ScreenPipeline.dockBundleIdentifier else {
            noteSkip("Mission Control")
            noteServed()
            return .refused
        }
        // Asked before the window is resolved so an app that must never be read costs no
        // WindowServer enumeration, and asked again below once there is a title to judge.
        guard !ScreenPipeline.isOwnOutput(appName: appName, bundleID: bundleID, title: nil) else {
            noteSkip("own output: \(appName)")
            // A refusal of our own, taken before the WindowServer is ever asked. It says nothing
            // about whether capture works, so it must neither arm nor advance the stall clock —
            // otherwise an hour in front of Claude Desktop would raise a false alarm.
            noteServed()
            return .refused
        }
        if let reason = exclusions.exclusionReason(for: CaptureSubject(bundleID: bundleID, appName: appName)) {
            noteSkip(reason.logDescription)
            noteServed()
            return .refused
        }

        let front = await activeWindow(pid: frontApp.processIdentifier)
        guard !Task.isCancelled else { return .standDown }
        guard let front else {
            // **Not** served. A frontmost application whose windows are invisible to
            // `SCShareableContent` is the signature of a window-server connection that no longer
            // carries capture rights, which is what a grant dropped mid-life leaves behind.
            noteSkip("frontmost app has no capturable window: \(appName)")
            reportStall()
            return .unavailable
        }
        let window = front.window

        // Which window the pixels are about to come from, taken from the same snapshot the capture
        // is filtered on. Everything read out of the accessibility API below has to belong to *this*
        // window before it may describe this frame — see ``AXWindowMatch``.
        let capturedWindow = CapturedWindow(
            frame: window.frame, title: window.title, wasOnlyWindow: front.isSole)

        // Titles are stored and indexed exactly like OCR text, and a terminal title carrying
        // `--token=…` or a callback URL is the same leak, so the same scrub runs before this value
        // is compared, emitted, or written.
        let windowTitle = Redaction.scrub(window.title ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty

        guard !ScreenPipeline.isOwnOutput(appName: appName, bundleID: bundleID, title: windowTitle) else {
            noteSkip("own output: \(appName)")
            noteServed()
            return .refused
        }
        let subject = CaptureSubject(
            bundleID: bundleID,
            appName: appName,
            windowTitle: windowTitle,
            url: await Self.pageHost(
                pid: frontApp.processIdentifier,
                bundleID: bundleID,
                appName: appName,
                window: capturedWindow))
        guard !Task.isCancelled else { return .standDown }
        let admission = exclusions.admit(subject)
        guard let ticket = admission.ticket else {
            noteSkip(admission.reason?.logDescription ?? "excluded")
            noteServed()
            return .refused
        }

        let image = await capture(window)
        guard !Task.isCancelled else { return .standDown }
        guard let image else {
            // `capture` already logged; this is the second of the three refusal signatures.
            reportStall()
            return .unavailable
        }
        lastSkipReason = nil
        // Pixels came back, so the WindowServer is answering this process. The one signal in the
        // whole tick that proves the screen half is genuinely alive — deliberately taken here and
        // not at `emit`, because deduplication legitimately suppresses most frames and a healthy
        // watcher looking at one unchanging document would otherwise look stalled.
        noteServed()
        // …and the same pixels are the only unarguable answer to "is Screen Recording granted".
        // Stamped here rather than only where a frame is stored, for the same reason: a
        // deduplicated frame is still a frame this process was allowed to take.
        // `Permissions.check(.screen)` prefers this to `CGPreflightScreenCaptureAccess`, which
        // reads false for a re-signed bundle that is demonstrably capturing.
        Permissions.noteCaptureSucceeded(.screen)
        reportStandDown(nil)

        let capturedAt = ContextTime.now
        let hash = ScreenPipeline.dHash(of: image)
        let seenRecently = recentHashes.contains { ScreenPipeline.isSameScreen(hash, $0) }
        // The gate has no ceiling of its own: a screen that stays inside `dedupeDistance` of one
        // already in the ring is suppressed for as long as it stays there, which for a document
        // being read is forever. This is that ceiling.
        let forced = seenRecently
            && ScreenPipeline.isForceDue(lastFullPassAt: lastFullPassAt, now: capturedAt)

        if seenRecently && !forced {
            // Idle or oscillating screen: no OCR, no image, and no row at all unless the user moved
            // to a different window — a duplicate row every 3 seconds would bury the timeline it is
            // meant to be.
            if appName != lastAppName || windowTitle != lastWindowTitle {
                return emit(
                    Frame(
                        capturedAt: capturedAt,
                        appName: appName,
                        bundleId: bundleID.nilIfEmpty,
                        windowTitle: windowTitle),
                    ticket: ticket,
                    axNodes: [])
            }
            return .suppressed
        }
        // Only genuinely new screens enter the ring — it is a memory of *distinct* screens, and a
        // forced capture is by definition one already in it. Re-adding it would evict a real
        // oscillation phase and hand the idle OCR cost straight back.
        if !seenRecently { remember(hash) }
        // Stamped before the pipeline runs rather than after it decides: the attempt is what costs,
        // so the next force is due a full interval from here whatever this one concludes.
        lastFullPassAt = capturedAt

        // Whether this window is already the newest row on the timeline. Computed here because the
        // decision it feeds — is there enough new text to be worth a row — has to be made before
        // the image is even encoded, and `lastAppName`/`lastWindowTitle` belong to this actor.
        let repeatsLastStoredWindow = appName == lastAppName && windowTitle == lastWindowTitle

        let pid = frontApp.processIdentifier
        let captured = CapturedImage(image: image)
        let processed = await Task.detached(priority: .utility) {
            ScreenPipeline.process(
                captured,
                repeatsLastStoredWindow: repeatsLastStoredWindow,
                pid: pid,
                window: capturedWindow
            )
        }.value

        guard !Task.isCancelled else { return .standDown }
        guard let processed else {
            // Pixels moved but no readable text arrived, in a window that is already the last row
            // stored — a spinner advancing, a progress bar filling, a repaint. The row would say
            // nothing the row before it does not already say, so it costs a row, an image, and an FTS
            // entry for nothing.
            return .lowSignal
        }

        return emit(
            Frame(
                capturedAt: capturedAt,
                appName: appName,
                // Already read at the top of the tick for the exclusion checks and, until now,
                // thrown away. It is the only reliable key back to the app on disk — the timeline
                // draws its icon from it rather than guessing at `<appName>.app` in a list of
                // directories. Empty becomes nil so "not recorded" stays one value in the column.
                bundleId: bundleID.nilIfEmpty,
                windowTitle: windowTitle,
                ocrText: processed.ocrText,
                axText: processed.axText,
                axRootHash: processed.axRootHash
            ),
            ticket: ticket,
            axNodes: processed.axNodes,
            // Encoded, not written. `emit` decides whether these bytes are ever allowed on disk.
            imageData: processed.imageData
        )
    }

    /// What this tick means for anything showing the user whether capture is live.
    ///
    /// Pure, and separate from the tick, because the sentence is a promise about a setting and a
    /// threshold rather than a log line: the switch's own words are "suspends recording when no
    /// keyboard or mouse activity is detected", and the app has to say so where the user can see it.
    /// Nil means capture is live — including when the switch is off, which is the case a "was the
    /// machine idle" question alone would get wrong.
    nonisolated static func idlePauseReason(pausesOnInactivity: Bool, isIdle: Bool) -> String? {
        guard pausesOnInactivity, isIdle else { return nil }
        return CaptureActivity.pausedSentence
    }

    /// Announces a change in why capture is standing down. Repeats are swallowed: this is called on
    /// every tick, and re-publishing an unchanged value would re-write the heartbeat file every
    /// three seconds for as long as a machine sits idle.
    func reportStandDown(_ next: ScreenStandDown?) {
        guard standDown != next else { return }
        standDown = next
        // A grant that was working and has stopped is the one event here that has to still be in
        // the log tomorrow — `info` is evicted from the unified log within minutes, which is why
        // the twenty-nine-hour outage left one line and no trace of what happened next.
        if let next, case .blocked(let block) = next, block.isRegression {
            ContextLog.milestone(block.reason, "screen")
        }
        onStandDown?(next)
    }

    /// The WindowServer answered — or was never asked, because this app declined the window itself.
    /// Either way the stall clock starts again from here.
    private func noteServed() {
        lastServedAt = ContextTime.now
    }

    /// One tick that tried and got nothing. Raises the alarm once the silence has lasted longer than
    /// ``stallSeconds``, and says nothing at all before that — a single failed capture is ordinary,
    /// and a recorder that cries about every one of them teaches its user to ignore it.
    private func reportStall() {
        guard let reason = Self.stallReason(lastServedAt: lastServedAt, now: ContextTime.now) else {
            return
        }
        reportStandDown(.stalled(reason))
    }

    /// Records a screen we have now seen, evicting the oldest once the ring is full.
    private func remember(_ hash: UInt64) {
        recentHashes.append(hash)
        if recentHashes.count > ScreenPipeline.recentScreenMemory {
            recentHashes.removeFirst()
        }
    }

    /// The one place an observation becomes durable, and the order is the whole of it.
    ///
    /// Judge, then check that anybody is still listening, then write the bytes, then hand the rows
    /// over — with no suspension point anywhere between the judgement and the write. That is why the
    /// image arrives here as encoded `Data` rather than as a path: encoding is expensive and belongs
    /// off the main actor, but *writing* used to happen there too, four lines after a comment
    /// promising that "a frame nobody stores must leave nothing behind". It did leave something
    /// behind — an excluded website's screenshot went to disk and was unlinked a moment later, which
    /// is not the same thing as never having been written, and no `frames` row ever referenced it,
    /// so nothing would have cleaned it up if the unlink had failed.
    ///
    /// Internal rather than private because this ordering is the property under test.
    @discardableResult
    func emit(
        _ frame: Frame, ticket: CaptureTicket, axNodes: [AXNodeRecord], imageData: Data? = nil
    ) -> TickOutcome {
        var frame = frame
        // Re-judged with the accessibility text, not merely revalidated against the subject the
        // ticket was minted from. That text is read after admission — it is the one piece of
        // evidence about *which site this was* that the gate has never seen, and writing it
        // unexamined is how an `axText` carrying an excluded domain reached a permanent, searchable
        // database. The engine only consults it when no address could be read; see `websiteReason`.
        if let reason = exclusions.revalidate(ticket, pageText: frame.axText) {
            // Carries no image path: nothing has been written yet, and this is the reason why. The
            // call stays for its log line and as the barrier for any future caller that does arrive
            // here with bytes already on disk.
            exclusions.discard(frame, reason: reason)
            noteSkip(reason.logDescription)
            return .refused
        }
        // Nobody left to hand this to: capture was stopped while the tick was suspended in OCR or in
        // an accessibility walk, which is seconds of work. Returning before the write is what stops
        // a stopped recorder from leaving a screenshot — and an accessibility subtree — behind it.
        guard let onFrame else { return .refused }

        if let imageData { frame.imagePath = writeImage(imageData, frame.capturedAt) }
        // Nodes before the frame, always. The frame carries a root hash into a table those rows have
        // to be in already, and both writes land on the same serialised queue in the order they are
        // handed over — so a frame is never stored pointing at a subtree nobody wrote.
        if !axNodes.isEmpty { onAXNodes?(axNodes) }
        lastAppName = frame.appName
        lastWindowTitle = frame.windowTitle
        onFrame(frame)
        return .stored
    }

    // MARK: - Window resolution

    /// `SCShareableContent.excludingDesktopWindows` walks every on-screen window through the
    /// WindowServer. At this cadence that contends with other capture apps (Zoom share, CleanShot,
    /// Loom) and shows up as UI stalls, so one snapshot is reused for `shareableContentTTL`.
    private func shareableContent(forceRefresh: Bool) async -> SCShareableContent? {
        // Already refused, by this same API, in this same process. Asking again cannot change the
        // answer — capture rights are settled at connection time — and every ask is a TCC request
        // macOS answers with the "would like to record this computer's screen and audio" alert. This
        // is what bounds a whole launch to one refused request: the tick gate stands down from the
        // next tick on, and this stops the second, forced refresh inside the tick that was refused.
        guard !Permissions.screenCaptureWasDeclined else { return nil }
        if !forceRefresh,
            let cachedContent,
            let cachedContentAt,
            Date().timeIntervalSince(cachedContentAt) < ScreenPipeline.shareableContentTTL
        {
            return cachedContent
        }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
            cachedContent = content
            cachedContentAt = Date()
            return content
        } catch {
            Self.noteIfDeclined(error)
            noteError("Shareable content unavailable: \(error.localizedDescription)")
            return nil
        }
    }

    /// **Tells a TCC refusal apart from the WindowServer having a bad moment.**
    ///
    /// Most capture failures are ordinary and recoverable — a window that closed mid-request, a
    /// display reconfiguration, a fast user switch — and the stall clock already handles those. One
    /// is not: `userDeclined` is macOS saying this process may not capture, whatever TCC's records
    /// say about the bundle, and it is the error the system alert is raised alongside. Recording it
    /// is the difference between one refused request per launch and one every three seconds forever.
    private static func noteIfDeclined(_ error: Error) {
        let error = error as NSError
        guard error.domain == SCStreamErrorDomain,
            error.code == SCStreamError.Code.userDeclined.rawValue
        else { return }
        Permissions.noteScreenCaptureDeclined()
    }

    private func activeWindow(pid: pid_t) async -> FrontWindow? {
        if let content = await shareableContent(forceRefresh: false),
            let window = ScreenPipeline.frontWindow(in: content, pid: pid)
        {
            return window
        }
        // The app opened its window inside the cache window. One forced refresh is cheaper than
        // losing the first few seconds of everything the user newly opens.
        guard let fresh = await shareableContent(forceRefresh: true) else { return nil }
        return ScreenPipeline.frontWindow(in: fresh, pid: pid)
    }

    /// The host the captured window is showing, read before the gate judges it.
    ///
    /// The whole point is the *before*. `ExclusionSet.websiteReason` has always been able to match a
    /// URL; nothing had ever put one on a `CaptureSubject`, so "exclude this website" fell through
    /// to matching the hostname against the window title — which browsers do not put there. Measured
    /// on this machine's database: 0 of 955 browser frames yielded a host from the title. The
    /// exclusion protected nothing.
    ///
    /// Four things bound the cost and the blast radius, because this runs on the way to every
    /// capture:
    ///
    /// - **Browsers only.** A website exclusion is about websites, and `websiteReason` already
    ///   refuses to read a domain out of a non-browser window. Asking every editor and terminal for
    ///   an address would be inter-process traffic spent on a question with no answer.
    /// - **Off the main actor**, like the tree walk that follows it, because every attribute read is
    ///   a synchronous message to an application that may be beachballing.
    /// - **Bounded** by ``AXCaptureLimits/urlProbe``, and by `AXElement.messagingTimeout` inside a
    ///   single read, which is the half a wall clock checked between elements cannot provide.
    /// - **The captured window only.** Read from whichever window the application says is *focused*,
    ///   this answered about a different window than the one being stored — and a wrong address is
    ///   worse than none, because an address outranks the page text beneath it and therefore
    ///   silences the tier that measurably works. `AXElement.window(pid:matching:)` will not answer
    ///   unless it can show that the window it read is the window that was captured.
    ///
    /// Nil when Accessibility is not granted, when the captured window cannot be identified, when
    /// the window answers nothing, or when the walk runs out of budget. Nil is not "no exclusion
    /// applies": it drops the gate back to the title, and then to the window's own text once
    /// ``emit(_:ticket:axNodes:imageData:)`` has it.
    private static func pageHost(
        pid: pid_t, bundleID: String, appName: String, window: CapturedWindow
    ) async -> String? {
        guard PrivateBrowsing.isBrowser(bundleID: bundleID, appName: appName),
            Permissions.check(.accessibility)
        else { return nil }
        return await Task.detached(priority: .utility) {
            guard let matched = AXElement.window(pid: pid, matching: window) else { return nil }
            return AccessibilityTree.pageHost(of: matched)
        }.value
    }

    private func capture(_ window: SCWindow) async -> CGImage? {
        let request: CachedCapture
        let key = CaptureRequestKey(window: window)
        if let cachedCapture, cachedCapture.key == key {
            request = cachedCapture
        } else {
            // The filter, not `window.frame`, is the authority on what will actually be captured and
            // at what backing scale — the frame knows neither. Both properties are macOS 14.0+ and the
            // deployment floor here is 14.4.
            let filter = SCContentFilter(desktopIndependentWindow: window)
            guard
                let size = ScreenPipeline.captureSize(
                    for: filter.contentRect,
                    pointPixelScale: CGFloat(filter.pointPixelScale)
                )
            else {
                cachedCapture = nil
                noteSkip("window has no area")
                return nil
            }

            let config = SCStreamConfiguration()
            config.width = size.width
            config.height = size.height
            config.scalesToFit = true
            config.showsCursor = false
            // Asking for more pixels than the nominal size is pointless if the source is downsampled
            // first, so take the native backing store.
            config.captureResolution = .best
            request = CachedCapture(key: key, filter: filter, configuration: config)
            cachedCapture = request
        }

        do {
            return try await SCScreenshotManager.captureImage(
                contentFilter: request.filter,
                configuration: request.configuration
            )
        } catch {
            // Do not carry a filter/configuration across a failed WindowServer request. The next
            // tick gets a fresh one-shot request and can recover from a stale connection or window.
            if cachedCapture?.key == request.key, cachedCapture?.filter === request.filter {
                cachedCapture = nil
            }
            // Judged before the cancellation check: a refusal is the same refusal whether or not the
            // watcher was being torn down as it arrived, and the watcher that replaces this one has
            // to know rather than start the retry loop over.
            Self.noteIfDeclined(error)
            if !Task.isCancelled {
                noteError("Capture failed: \(error.localizedDescription)")
            }
            return nil
        }
    }

    // MARK: - Logging that cannot spam

    /// A skip repeats every tick for as long as the condition holds; log only the transition.
    private func noteSkip(_ reason: String) {
        guard lastSkipReason != reason else { return }
        lastSkipReason = reason
        ContextLog.info("Skipping capture: \(reason)", "screen")
    }

    private func noteError(_ message: String) {
        let now = Date()
        if let lastErrorLoggedAt, now.timeIntervalSince(lastErrorLoggedAt) < 60 { return }
        lastErrorLoggedAt = now
        ContextLog.error(message, "screen")
    }
}

// MARK: - What the ticks did

/// What one tick of the screen loop concluded. Exactly one is recorded per tick.
enum TickOutcome: String, CaseIterable {
    /// The loop declined to look at all: no grant, screen locked, idle pause, nothing frontmost.
    case standDown
    /// This app refused the window — its own output, an exclusion, Mission Control.
    case refused
    /// The WindowServer had nothing to give: no capturable window, or the capture failed.
    case unavailable
    /// Pixels came back and the dedup gate recognised them.
    case suppressed
    /// Pixels came back, were read, and said nothing the newest row does not already say.
    case lowSignal
    /// A row was written.
    case stored
}

/// A running count of what the screen loop is doing with its ticks.
///
/// **This exists because the frame-rate defect was invisible for want of exactly this number.** The
/// app captured roughly half as many frames a day as the recorder it is meant to match, and nothing
/// anywhere distinguished "we are not firing often enough" from "we are firing and throwing half of
/// it away" — the two have completely different fixes, and the log could not tell them apart. Rows
/// per hour are observable from the database; *attempts* per hour were observable from nowhere.
///
/// Deliberately a count and not a per-tick log line: a tick every three seconds for the life of the
/// machine is 28,800 lines a day, which is not evidence, it is noise that buries evidence.
struct CaptureCensus {
    private(set) var counts: [TickOutcome: Int] = [:]
    private(set) var ticks = 0

    /// Ticks between summaries — ten minutes at the 3 s cadence.
    static let reportEvery = 200

    /// Records one tick and returns a line to log when the census is due, or nil.
    mutating func record(_ outcome: TickOutcome) -> String? {
        counts[outcome, default: 0] += 1
        ticks += 1
        guard ticks >= Self.reportEvery else { return nil }
        let line = summary
        counts.removeAll()
        ticks = 0
        return line
    }

    mutating func reset() {
        counts.removeAll()
        ticks = 0
    }

    /// Attempts, rows, and where the rest of the attempts went — the whole comparison in one line.
    var summary: String {
        let attempted = (counts[.suppressed] ?? 0) + (counts[.lowSignal] ?? 0) + (counts[.stored] ?? 0)
        let breakdown = TickOutcome.allCases
            .compactMap { outcome in counts[outcome].map { "\(outcome.rawValue) \($0)" } }
            .joined(separator: ", ")
        return "Capture census: \(ticks) ticks, \(attempted) reached the screen, "
            + "\(counts[.stored] ?? 0) stored — \(breakdown)"
    }
}

// MARK: - Why the screen half is quiet

/// The three reasons screen capture is not producing, kept apart because the app must *do*
/// something different about each of them.
///
/// A single optional sentence could not: the engine has to know whether to keep calling itself
/// healthy (a pause), to put something in front of the user (a block), or to try recycling the
/// watcher (a stall). Collapsing them into `String?` is what let a dropped Screen Recording grant
/// read as a deliberate pause and then, having no shape to be reported in at all, read as nothing.
enum ScreenStandDown: Equatable {
    /// The switch or the system says stop for now, and nothing has failed. The user is away, the
    /// screen is locked. Capture resumes by itself and the app is not degraded by it.
    case paused(String)
    /// Needs the user: the grant is gone, was never given, or cannot be used until this process is
    /// relaunched. Carries the block so the copy and the log level are decided in one place.
    case blocked(Permissions.ScreenBlock)
    /// Believed running, and the WindowServer has answered nothing for longer than
    /// ``ScreenWatcher/stallSeconds``.
    case stalled(String)

    var reason: String {
        switch self {
        case .paused(let sentence): return sentence
        case .blocked(let block): return block.reason
        case .stalled(let sentence): return sentence
        }
    }
}

// MARK: - Is anybody there

/// When a Mac has been left alone long enough that capturing it is recording an empty room.
///
/// Internal rather than file-private because the threshold is a product decision with a test on it,
/// and the decision itself has to be assertable without a WindowServer.
enum CaptureActivity {

    /// How long the machine must go untouched before "Pause on Inactivity" stops capture.
    ///
    /// Five minutes, and the number is bounded from below by this pipeline's own behaviour rather
    /// than picked round. **Reading is inactivity.** `ScreenPipeline.forceCaptureInterval` exists
    /// precisely because a person sitting still in front of a document produced no rows at all, and
    /// a short idle threshold would delete that same activity a second time — a minute of reading a
    /// contract is not an absence, and an always-on recorder that forgets the deepest work of the
    /// day is worse than one that keeps a few idle frames.
    ///
    /// Five is also what this app already means by "the user has gone": `SessionPolicy.gapSeconds`
    /// ends a conversation after five minutes of silence. One answer to that question is better than
    /// two that can drift.
    ///
    /// What it costs: a video watched without touching anything stops being captured after five
    /// minutes. That is the honest reading of the switch's own promise — "suspends recording when no
    /// keyboard or mouse activity is detected" — and it is off by a toggle.
    static let idleThreshold: TimeInterval = 300

    /// What the menu bar and the heartbeat file say while this gate is holding capture down.
    ///
    /// Derived from ``idleThreshold`` rather than written out, because the two drifting apart is the
    /// specific way this sentence would become a lie: a threshold moved to two minutes and a
    /// sentence still promising five is worse than no sentence, since the user would go looking for
    /// three minutes of capture that were never taken.
    ///
    /// Named as a *pause* rather than an error. Nothing has failed — this is the switch doing
    /// exactly what it says — and the app's job here is only to stop claiming it is recording.
    static var pausedSentence: String {
        let minutes = (idleThreshold / 60).rounded()
        guard minutes >= 1, minutes * 60 == idleThreshold else {
            let seconds = Int(idleThreshold.rounded())
            return "Paused — no activity for \(seconds) second\(seconds == 1 ? "" : "s")"
        }
        let whole = Int(minutes)
        return "Paused — no activity for \(whole) minute\(whole == 1 ? "" : "s")"
    }

    /// Seconds since the last keyboard, mouse or trackpad event anywhere in this login session.
    ///
    /// `.combinedSessionState` rather than `.hidSystemState` so that a wake from another input
    /// source counts, and `kCGAnyInputEventType` — spelled by hand because the Swift overlay does
    /// not import the C macro — so that a mouse *move* is activity, not just a click.
    static func secondsSinceInput() -> TimeInterval {
        CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: anyInputEvent)
    }

    private static let anyInputEvent = CGEventType(rawValue: ~0)!

    /// Whether capture should stand down.
    ///
    /// **This cannot wedge capture off**, and that property is the reason it is written as a pure
    /// function of a number read fresh on every tick rather than as a state machine. There is no
    /// paused flag, nothing is cleared, and no timer has to fire: any input at all resets the
    /// counter the WindowServer keeps, so the next tick — at most one interval later — captures
    /// normally. The first tick after a pause is also always a full pass, because more than
    /// `forceCaptureInterval` will have elapsed and `isForceDue` therefore says yes even if the
    /// screen never changed.
    ///
    /// A negative or non-finite reading means the clock moved under us rather than that the user has
    /// been gone for a negative time, and is treated as activity: the direction that keeps recording.
    static func isIdle(
        secondsSinceInput seconds: TimeInterval = secondsSinceInput(),
        threshold: TimeInterval = idleThreshold
    ) -> Bool {
        guard seconds.isFinite, seconds >= 0 else { return false }
        return seconds >= threshold
    }
}

// MARK: - Off-actor pipeline

/// The window a tick will capture, and whether the application had any other.
private struct FrontWindow {
    let window: SCWindow
    /// Exactly one capturable window belonged to this application in the snapshot.
    let isSole: Bool
}

/// A `CGImage` handed to a background task. CoreGraphics images are immutable once created, so
/// crossing an isolation boundary with one is safe; the compiler just cannot prove it.
private struct CapturedImage: @unchecked Sendable {
    let image: CGImage
}

private struct ProcessedFrame: Sendable {
    let ocrText: String?
    /// The stored picture, encoded and **not written**. Encoding is the expensive half and belongs
    /// off the main actor; the write belongs after the last judgement, which is `ScreenWatcher.emit`.
    let imageData: Data?
    let axText: String?
    let axRootHash: Data?
    let axNodes: [AXNodeRecord]
}

/// Vision writes its observations from inside `perform`, synchronously, before it returns — so this
/// box is never touched from two threads even though the block signature allows it.
private final class TextSink: @unchecked Sendable {
    var lines: [String] = []
    var failure: Error?
}

/// Everything that must run off the main actor, plus the pure policy that decides what is worth
/// capturing at all. Declared at file scope so none of it inherits `ScreenWatcher`'s isolation.
private enum ScreenPipeline {

    // MARK: Tunables

    /// Longest side of the image handed to Vision.
    ///
    /// Split from the *stored* image's longest side because one constant governing both meant OCR
    /// resolution could not be tuned without changing storage, and the storage bound won. That split
    /// is also what lets Settings > Capture Quality exist at all: the tiles move the stored picture
    /// and this stays where the measurement put it, which is exactly what the pane promises when it
    /// says text search is unaffected.
    ///
    /// Measured, not chosen: `.accurate` recognition of a screenful of UI text is non-monotonic in
    /// input size and peaks near 2400 px on the longest side. On this machine's built-in display,
    /// identifier recall was 88% at the 1512 px that shipped, 96% at 2400 px, and **75% at the
    /// native 3024 px** — so "just OCR the native image" is worse than the defect it would be
    /// fixing, and both sides of the band are bad. Latency is flat across the whole range
    /// (0.67–0.96 s) because Vision's cost tracks the number of text regions rather than the pixel
    /// count, so this is an accuracy decision and not a battery one. It is an empirical optimum
    /// from one fixture family on one machine: re-run the sweep in `docs/ocr-quality.md` §3 before
    /// moving it, and re-run it whenever the pinned Vision revision changes.
    static let ocrMaxPixelSize = 2400

    /// Longest accessibility text stored per frame.
    ///
    /// Generous next to a window title and mean next to a document: the point is the labels, values
    /// and controls a person was actually looking at, not the whole scrollback of a text view. The
    /// walker's own per-node and total-text ceilings do most of this work already; this is the last
    /// bound before the column.
    static let maxAXTextCharacters = 8_000
    /// Titles can therefore lag reality by up to this long; the OCR text on the same row is always
    /// current, and the next tick corrects the title.
    static let shareableContentTTL: TimeInterval = 5
    /// Hamming distance below which two dHashes count as the same screen. Exact equality would be
    /// useless: a blinking caret or a ticking menu-bar clock flips a bit or two every tick and
    /// would force a full OCR pass on a screen nobody is touching. Empirically a spinner differs by
    /// 1 bit, a moved text cursor by ~4, and a real content change by 20+.
    ///
    /// That calibration was taken at the old capture size. `dHash` still renders to a fixed 9x8
    /// grid, but each cell now averages ~2.5x more source pixels, which should if anything make the
    /// hash steadier rather than noisier. `docs/ocr-quality.md` §4.3 asks for the two populations to
    /// be re-confirmed against logged hamming distances; ``forceCaptureInterval`` is what keeps a
    /// mis-calibration from being silent in the meantime, since no window can be suppressed forever.
    static let dedupeDistance = 5

    /// How many distinct recent screens a new capture is compared against.
    ///
    /// Eight covers the loops that actually occur — a two- or three-frame spinner, a window flipping
    /// between two states, an alt-tab back and forth — without being large enough to swallow real
    /// re-reading: at 3 s a tick, a screen has to be genuinely identical (within
    /// ``dedupeDistance``) to something inside the last handful of *different* screens to be
    /// skipped, and coming back to an unchanged window is not new information anyway. Only novel
    /// hashes enter the ring, so a spinner cannot flush the real screens out of it.
    static let recentScreenMemory = 8

    /// The longest a window may stay on screen without earning a row, however unchanged it looks.
    ///
    /// The ring answers "have we seen this screen" and nothing else, so it has no ceiling: a screen
    /// that never leaves the ``dedupeDistance`` ball around one of its entries is suppressed
    /// forever. That silently deleted the activity most worth remembering — measured against a
    /// rival recorder over the same two hours, Finder was missed *entirely* (1.8% of their capture,
    /// 0.0% of ours), Messages 11.7% vs 5.2%, Claude 10.7% vs 6.8%. Apps that sit still got
    /// suppressed, and sitting still in front of a document is what reading looks like.
    ///
    /// Sixty seconds, chosen against the consumer rather than picked round: `Queries.activity`
    /// closes an activity block when consecutive frames are more than 120 s apart. Forcing at half
    /// that keeps a continuously-viewed static window inside one unbroken block even when a tick is
    /// lost to a slow OCR pass or a missed window lookup, so "read one document for an hour" reads
    /// back as an hour rather than as absence. It also bounds the cost exactly: at most one extra
    /// OCR pass and one stored image per minute, a twentieth of what the 3 s tick could produce, and only
    /// while a window is otherwise being suppressed.
    static let forceCaptureInterval: Double = 60

    /// Letters and digits below which a frame is not worth a row of its own.
    ///
    /// Counted over content characters only, so spinner glyphs (`⠐`, `⠂`), box drawing, progress
    /// bars and window chrome score zero — which is what a tenth of the frames in the dogfooding
    /// database were. Twenty-five is roughly four short words: below any real sentence, above every
    /// decoration. It only ever applies when the window is *also* unchanged from the last stored
    /// frame, so the first sighting of a text-free window still gets recorded.
    static let minimumContentCharacters = 25

    static let dockBundleIdentifier = "com.apple.dock"

    /// Held for the process lifetime rather than built per request: a Swift array literal assigned
    /// to `recognitionLanguages` has call-frame lifetime, and Vision keeps enumerating the bridged
    /// NSArray on its own queue after the frame is gone (omi #5891, #5151 — a trap, not an error).
    static let recognitionLanguages: [String] = ["en-US"]

    // MARK: Not reading ourselves

    /// Claude Desktop. Anything else Anthropic ships is caught by the prefix below, because every
    /// bundle they ship is a surface where this assistant's own words are on screen.
    static let claudeDesktopBundleIdentifier = "com.anthropic.claudefordesktop"
    static let anthropicBundlePrefix = "com.anthropic."

    /// Terminal emulators, where Claude Code runs. The set exists only to gate the title check
    /// below: a terminal is otherwise ordinary and worth capturing.
    static let terminalBundleIdentifiers: Set<String> = [
        "com.apple.terminal",
        "com.googlecode.iterm2",
        "net.kovidgoyal.kitty",
        "com.mitchellh.ghostty",
        "io.alacritty",
        "org.alacritty",
        "com.github.wez.wezterm",
        "dev.warp.warp-stable",
        "dev.warp.warp-preview",
        "co.zeit.hyper",
        "org.tabby",
    ]

    /// Emulators ship under new bundle ids faster than a list can track; their names are stabler.
    static let terminalNameFragments = [
        "terminal", "iterm", "kitty", "ghostty", "alacritty", "wezterm", "warp", "hyper", "tabby",
    ]

    /// What marks a terminal window as one this assistant is running inside.
    ///
    /// There is no honest signal for "Claude Code is the process in this window" from outside it:
    /// the frontmost application is the emulator, not the CLI, and walking the process tree is a
    /// different permission and a different class of bug. The title is the cheap evidence available,
    /// and Claude Code writes its state into it — `✳` while it is working, and the word `claude` in
    /// the command-derived title most emulators set.
    ///
    /// **It catches:** a Terminal / iTerm2 / kitty / Ghostty / WezTerm / Alacritty / Warp / Hyper /
    /// Tabby window whose title mentions Claude or carries the `✳` marker. That is the shape of the
    /// 22-in-906 self-captures found in the database.
    ///
    /// **It does not catch:** Claude Code in an editor's integrated terminal (VS Code, Cursor,
    /// JetBrains) or inside a tmux/screen session that rewrites the title; an emulator configured to
    /// show only the working directory or the hostname; a background pane; or claude.ai in a browser
    /// tab. Nor does it distinguish "Claude Code is running here" from "this window happens to be in
    /// ~/claude-experiments" — a directory named after Claude loses its frames, which is the cheap
    /// side of the trade. The remaining hole is real, and the fix for it is a signal from the CLI
    /// rather than a longer list of guesses about titles.
    static let claudeCodeTitleMarkers = ["claude", "✳"]

    /// Windows whose text originates from this app or from Claude itself.
    ///
    /// Storing them is not a privacy problem, it is a correctness one: OCRing the assistant's own
    /// output back into the database means the next `recall` returns Claude's words as "context
    /// about the user's life", and every turn compounds the last one.
    static func isOwnOutput(appName: String, bundleID: String, title: String?) -> Bool {
        let bundle = bundleID.lowercased()
        let name = appName.lowercased()

        // `Bundle.main.bundleIdentifier` is nil under `swift run` and in tests, so the shipped id is
        // also compared literally — a dev build must not read itself either.
        if bundle == ContextPaths.bundleIdentifier { return true }
        if let own = Bundle.main.bundleIdentifier, bundleID == own { return true }

        if bundle == claudeDesktopBundleIdentifier || bundle.hasPrefix(anthropicBundlePrefix) {
            return true
        }
        // Claude Desktop as macOS reports its display name.
        if name == "claude" { return true }

        guard terminalBundleIdentifiers.contains(bundle)
            || terminalNameFragments.contains(where: { name.contains($0) })
        else { return false }

        guard let title = title?.lowercased() else { return false }
        return claudeCodeTitleMarkers.contains { title.contains($0) }
    }

    static func isScreenLocked() -> Bool {
        guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else { return false }
        if let locked = session["CGSSessionScreenIsLocked"] as? Bool, locked { return true }
        // Fast user switching: another account owns the console, so there is nothing of ours to read.
        if let onConsole = session["kCGSSessionOnConsoleKey"] as? Bool, !onConsole { return true }
        return false
    }

    // MARK: Window choice

    static func frontWindow(in content: SCShareableContent, pid: pid_t) -> FrontWindow? {
        let candidates = content.windows.filter { window in
            window.owningApplication?.processID == pid
                && window.windowLayer == 0
                && window.frame.width > 100
                && window.frame.height > 100
        }
        guard let largest = candidates.map({ $0.frame.width * $0.frame.height }).max() else {
            return nil
        }
        // `windows` comes back front-to-back, so among equally large windows the first one is the
        // one the user is looking at rather than the backmost (omi #6552).
        guard let window = candidates.first(where: { $0.frame.width * $0.frame.height == largest })
        else { return nil }
        // How many there were, not just which one won. It is the only cheap fact that says whether
        // "which window is this?" is even a question for this application — see
        // ``CapturedWindow/wasOnlyWindow``.
        return FrontWindow(window: window, isSole: candidates.count == 1)
    }

    /// Pixel dimensions to capture, preserving aspect ratio.
    ///
    /// `SCContentFilter.contentRect` is in **points** while `SCStreamConfiguration.width`/`.height`
    /// are in **pixels** ("output width as measured in pixels"), so passing the point size straight
    /// through captured a Retina window at 1x and halved every glyph before Vision ever saw it. The
    /// old `min(1, …)` clamp made it worse, because it could only ever shrink: a 1920 pt window
    /// went out at 1600 px — 0.83x of the points, 0.42x of the pixels actually on screen — and
    /// measured 19.6% CER with 32% identifier recall, two thirds of the searchable terms destroyed.
    ///
    /// So: scale *up* towards the backing store, cap at ``ocrMaxPixelSize``, and never go below 1x.
    /// Below 1x throws away text that was on the screen; above the cap accuracy falls again (see
    /// ``ocrMaxPixelSize``). The stored image is brought back down separately in ``writeFrameImage``.
    ///
    /// A zero-area window makes the ratio NaN, and `Int(NaN)` traps rather than throwing — so a
    /// degenerate frame is refused here instead of crashing the app.
    static func captureSize(for rect: CGRect, pointPixelScale: CGFloat) -> (width: Int, height: Int)? {
        guard rect.width > 0, rect.height > 0,
            rect.width.isFinite, rect.height.isFinite
        else { return nil }

        // A missing, non-finite or sub-1 scale would shrink the capture below the point size, which
        // is the bug being fixed — fall back to 1x rather than trusting it.
        let backing = (pointPixelScale.isFinite && pointPixelScale >= 1) ? pointPixelScale : 1
        let longestPoints = max(rect.width, rect.height)
        let target = min(longestPoints * backing, CGFloat(ocrMaxPixelSize))
        let factor = max(1, target / longestPoints)
        return (
            max(1, Int((rect.width * factor).rounded())),
            max(1, Int((rect.height * factor).rounded()))
        )
    }

    // MARK: Dedupe

    /// Perceptual difference hash: 9x8 grayscale, each pixel compared to its right neighbour.
    /// Localised motion (a cursor, a spinner) moves one or two bits; new content moves many.
    static func dHash(of image: CGImage) -> UInt64 {
        let width = 9
        let height = 8
        guard
            let context = CGContext(
                data: nil,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width,
                space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGImageAlphaInfo.none.rawValue
            )
        else { return 0 }

        context.interpolationQuality = .low
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

        guard let data = context.data else { return 0 }
        let pixels = data.assumingMemoryBound(to: UInt8.self)

        var hash: UInt64 = 0
        for row in 0..<height {
            for column in 0..<(width - 1) {
                let index = row * width + column
                if pixels[index] > pixels[index + 1] {
                    hash |= 1 << (row * (width - 1) + column)
                }
            }
        }
        return hash
    }

    static func isSameScreen(_ lhs: UInt64, _ rhs: UInt64) -> Bool {
        (lhs ^ rhs).nonzeroBitCount <= dedupeDistance
    }

    /// Whether the dedup gate has suppressed everything for long enough that the next frame must be
    /// stored regardless of how similar it looks. See ``forceCaptureInterval``.
    ///
    /// No prior pass means due: the first capture of a run is always worth storing.
    static func isForceDue(lastFullPassAt: Double?, now: Double) -> Bool {
        guard let lastFullPassAt else { return true }
        let elapsed = now - lastFullPassAt
        // Wall-clock, so an NTP correction or a wake from sleep can put `now` behind the last pass.
        // A backwards jump counts as due rather than wedging capture until real time catches up.
        return elapsed < 0 || elapsed >= forceCaptureInterval
    }

    // MARK: Off-main work

    /// Reads the frame and decides whether it earns a row. Nil means store nothing at all.
    ///
    /// Nothing here touches the filesystem. Everything expensive — OCR, the accessibility walk, the
    /// downscale and the HEIC encode — happens off the main actor, and the *write* happens after the
    /// caller's last judgement; see ``ScreenWatcher/emit(_:ticket:axNodes:imageData:)``.
    static func process(
        _ captured: CapturedImage,
        repeatsLastStoredWindow: Bool,
        pid: pid_t,
        window: CapturedWindow
    ) -> ProcessedFrame? {
        // Detached tasks run on the cooperative pool, which does not drain autorelease pools; the
        // CoreGraphics and Vision temporaries below would otherwise accumulate for the app's life.
        autoreleasepool { () -> ProcessedFrame? in
            let text = recognizeText(in: captured.image)

            // Judged before anything is encoded rather than after: a frame nobody stores must cost
            // nothing at all, and the encode is the most expensive step in the tick.
            if repeatsLastStoredWindow, contentLength(of: text) < minimumContentCharacters {
                return nil
            }

            // The same window, read rather than looked at. Done here, off the main actor, because
            // every attribute is a synchronous message to another process: an application that is
            // beachballing would otherwise stall the tick that is trying to observe it. The walker's
            // own wall-clock budget and `AXElement.messagingTimeout` are what bound that, and a
            // window that answers nothing simply leaves these nil — OCR above has already produced a
            // usable row either way.
            //
            // `window` rather than "whatever is focused": this text is stored on the same row as the
            // picture above and is judged by the exclusion gate as evidence about it, so reading it
            // from a different window of the same application both mixes two windows into one row
            // and hands the gate evidence about the wrong one.
            var axText: String?
            var axRootHash: Data?
            var axNodes: [AXNodeRecord] = []
            if Permissions.check(.accessibility),
               let element = AXElement.window(pid: pid, matching: window),
               let tree = AccessibilityTree.capture(element) {
                axText = AccessibilityTree
                    .flattenedText(of: tree, limit: maxAXTextCharacters)
                    .nilIfEmpty
                axRootHash = AccessibilityTree.rootHash(of: tree)
                axNodes = AccessibilityTree.records(of: tree)
            }

            let imageData = FrameImage.encoded(captured.image)
            if imageData == nil { ContextLog.error("Failed to encode frame image", "screen") }

            return ProcessedFrame(
                ocrText: text,
                imageData: imageData,
                axText: axText,
                axRootHash: axRootHash,
                axNodes: axNodes)
        }
    }

    /// Letters and digits in `text`, ignoring whitespace, punctuation and symbols.
    ///
    /// Symbols are what a low-signal frame is made of — a Braille spinner, a block-drawing progress
    /// bar, a row of window-chrome glyphs — and counting them would let exactly the frames this is
    /// meant to catch pass as content.
    static func contentLength(of text: String?) -> Int {
        guard let text else { return 0 }
        var count = 0
        for scalar in text.unicodeScalars where contentCharacters.contains(scalar) { count += 1 }
        return count
    }

    static let contentCharacters = CharacterSet.letters.union(.decimalDigits)

    /// OCR, scrubbed. The raw recognition result never leaves this function.
    ///
    /// This is the only place OCR text is produced, which is what makes "redact before the write"
    /// enforceable rather than a habit: there is no path from Vision to the database that could skip
    /// the scrub. Redacting afterwards would be theatre — the plaintext would already be in the
    /// file, in the WAL, and in any backup taken between the two.
    ///
    /// What this does *not* protect is the image written beside the row: it still holds the pixels
    /// the credential was drawn in. Images are not searched and not returned by any MCP tool, so a
    /// secret cannot be recalled out of one, but anyone with the frames directory can look. Fixing
    /// that means not writing the image when a scrub fires, which is a bigger behaviour change than
    /// this one and belongs with the retention policy.
    static func recognizeText(in image: CGImage) -> String? {
        let sink = TextSink()
        let request = VNRecognizeTextRequest { request, error in
            if let error {
                sink.failure = error
                return
            }
            guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
            // Defensive copy: Vision returns a bridged NSArray whose buffer can be released
            // underneath an enumeration, which traps the process instead of throwing (#5891, #5151).
            sink.lines = Array(observations).compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = recognitionLanguages

        // Pinned rather than left on whatever `currentRevision` the running OS ships. `frames_fts`
        // is durable and never re-OCR'd, so an OS update that changed the recogniser would split
        // the index down the middle: text stored last month stops matching text stored tomorrow,
        // unreproducibly, and nothing in the product could explain why. Revision 3 is the newest
        // this SDK defines and 1 and 2 are deprecated as of macOS 15, so this is a behavioural
        // no-op today — its entire job is to make a future revision 4 a decision with a
        // re-measurement attached rather than a silent corpus change.
        request.revision = VNRecognizeTextRequestRevision3

        // Explicitly the most permissive setting, and pinned for the same reason as the revision.
        //
        // Worth stating because the obvious value is wrong here: 1/32 (0.03125) is the default for
        // `VNDetectTextRectanglesRequest`, *not* for this request, whose documented and
        // probe-confirmed default is 0.0. The SDK is unambiguous — "if the minimum height is set to
        // 0.0 the image gets processed at the highest possible resolution with no downscaling …
        // the smallest technically readable text will be recognized". So there is no recall to buy
        // by lowering this: any non-zero value, 0.015 included, is a *raise* that makes Vision
        // downscale and loses exactly the dense IDE and terminal text such a change is meant to
        // win. The only lever on glyph height is the image handed in, which is `captureSize`.
        request.minimumTextHeight = 0

        do {
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        } catch {
            ContextLog.error("OCR failed: \(error.localizedDescription)", "screen")
            return nil
        }
        if let failure = sink.failure {
            ContextLog.error("OCR failed: \(failure.localizedDescription)", "screen")
            return nil
        }
        return Redaction.scrub(sink.lines.joined(separator: "\n"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty
    }

    /// Puts already-encoded bytes on disk, and does nothing else.
    ///
    /// The bytes arrive encoded because *when* they are produced and *when* they are written are two
    /// different decisions: encoding is expensive and belongs off the main actor, while the write is
    /// the last irreversible step of a tick and belongs after the last judgement, with nothing
    /// suspended in between. See ``ScreenWatcher/emit(_:ticket:axNodes:imageData:)``.
    ///
    /// The stored size and fidelity were applied by ``FrameImage/encoded(_:)``. They govern
    /// **storage only** — they must never decide what Vision sees, which is why the downscale
    /// happens after OCR, from an image captured at ``ocrMaxPixelSize``.
    ///
    /// ``FrameImage/Quality`` (1600 px) is what the retention measurement was taken at, and the
    /// reason the bounds are where they are: capture burns ~200 MB a day, `defaultRetentionDays` is
    /// 30, and `defaultFrameBytesCap` is 4 GB. As JPEG that is ~6 GB for the window the policy
    /// promises, so the byte cap bit around three weeks in and silently deleted the rest — the user
    /// lost history the settings told them they had. At the default tile the same 30 days is ~2.2
    /// GB, under the cap with room for a heavier week, and the promise holds. A user who picks
    /// **Best Quality** is choosing to spend that headroom, which is a choice they are allowed to
    /// make and the Storage pane is what bounds.
    static func writeFrameImage(_ data: Data, capturedAt: Double) -> String? {
        // The extension changes with the format, and nothing downstream cares: `frames.imagePath`
        // is opaque text, and both prune paths delete by path rather than by suffix. So the older
        // `.jpg` files already on disk keep working and expire on the same schedule — the format
        // change needs no migration and no dual-read path.
        let directory = ContextPaths.framesDirectory(for: capturedAt)
        let name = "frame_\(fileStampFormatter.string(from: Date(timeIntervalSince1970: capturedAt))).heic"
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            ContextPaths.setPermissions(directory, mode: 0o700)
            let url = directory.appendingPathComponent(name)
            try data.write(to: url, options: .atomic)
            ContextPaths.setPermissions(url, mode: 0o600)
            return url.path
        } catch {
            ContextLog.error("Failed to write frame image: \(error.localizedDescription)", "screen")
            return nil
        }
    }

    static let fileStampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HHmmss_SSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()
}

// MARK: - The stored picture

/// Turning a captured screen into the bytes that go on disk, at the fidelity the user chose.
///
/// Separate from ``ScreenPipeline`` because it is the one part of the write path that is pure: an
/// image in, bytes out, no clock, no filesystem, no WindowServer. That is what makes "the four
/// Capture Quality tiles actually move the stored picture" assertable rather than merely written
/// down — the tiles quoted four pixel sizes for a pipeline that hard-coded one.
enum FrameImage {

    /// **How large and how compressed a stored screenshot is — one answer, for everybody.**
    ///
    /// This was four answers behind a Capture Quality tile row (2400/1600/1280/1024 px at HEIC
    /// q0.40/0.20/0.15/0.10). The tiles are gone on the report *"don't give capture quality
    /// option"*, and these two numbers are what **Default** always was: the setting every install
    /// shipped on, the one `ScreenWatcher`'s measured storage table was taken at, and the one
    /// `docs/ocr-quality.md` and the Storage pane's retention figures are written against.
    ///
    /// Deleting the choice is not the same as deleting the knob — the pipeline still downscales and
    /// still encodes, and `CapturePacingTests` still asserts that it does, because a pipeline that
    /// quietly stopped resizing would look identical from the outside until the disk filled.
    enum Quality {
        /// Longest side of the stored picture, in pixels. OCR reads a separate, larger image
        /// (``ScreenPipeline/ocrMaxPixelSize``) before this one is written, so the text of a user's
        /// history does not depend on this number.
        static let longestSide = 1600
        /// HEIC lossy-compression quality. HEIC's scale is not JPEG's — see ``data(from:)``.
        static let compression = 0.20
    }

    /// The bytes to write for `image`: downscaled, then encoded.
    ///
    /// Downscale first. Encoding the full-size capture and shrinking afterwards would spend the
    /// compression budget on pixels that are about to be thrown away.
    static func encoded(_ image: CGImage) -> Data? {
        let sized = downscaled(image, longestSide: Quality.longestSide) ?? image
        return data(from: sized)
    }

    /// Brings the stored frame image down to the selected tile's longest side.
    ///
    /// This used to be a no-op, because the capture itself was clamped to 1600 — which is precisely
    /// why the OCR input size could not be raised without inflating storage. Now the capture is
    /// sized for Vision (up to `ocrMaxPixelSize`) and this is the only thing deciding how large the
    /// stored image is.
    static func downscaled(_ image: CGImage, longestSide: Int) -> CGImage? {
        let longest = max(image.width, image.height)
        guard longest > longestSide else { return nil }

        let scale = CGFloat(longestSide) / CGFloat(longest)
        let width = max(1, Int((CGFloat(image.width) * scale).rounded()))
        let height = max(1, Int((CGFloat(image.height) * scale).rounded()))
        guard
            let context = CGContext(
                data: nil,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: 0,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            )
        else { return nil }

        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return context.makeImage()
    }

    /// Encodes the stored frame as HEIC at the selected fidelity.
    ///
    /// ``FrameImage/Quality/compression`` was picked by measurement, not taste. Encoding 60 real
    /// frames from this machine through this exact path — same downscale, same `CGImageDestination`
    /// call — gave, per frame:
    ///
    ///     jpeg q0.50   183.1 KB     heic q0.30    90.3 KB  (-51%)
    ///     heic q0.50   131.1 KB     heic q0.25    80.3 KB  (-56%)
    ///     heic q0.40   110.2 KB     heic q0.20    68.4 KB  (-63%)
    ///
    /// Note HEIC's quality scale is not JPEG's: 0.5 buys only 28%, and matching a "low" preset from
    /// `sips` takes roughly 0.15 — which is why the stored quality is 0.20 rather than one of the
    /// round JPEG-shaped numbers a reader would expect. Anyone re-tuning it must re-measure.
    ///
    /// **Fidelity used to be the cheap side of this trade and no longer is.** The note here once
    /// read "nothing decodes these files: no MCP tool returns pixels and the uploader sends only
    /// text" — true when it was written, and false since the `look` tool started handing these
    /// frames to Claude as images. This number is now also the ceiling on what a model can read off
    /// a screenshot, and small UI text is the first thing to go, so re-tuning it downward is a
    /// legibility decision as much as a storage one.
    ///
    /// OCR reads a separate, larger image (``ocrMaxPixelSize``) before this one is written and is
    /// untouched by it.
    static func data(from image: CGImage) -> Data? {
        let data = NSMutableData()
        guard
            let destination = CGImageDestinationCreateWithData(
                data as CFMutableData,
                "public.heic" as CFString,
                1,
                nil
            )
        else { return nil }

        CGImageDestinationAddImage(
            destination,
            image,
            [kCGImageDestinationLossyCompressionQuality: Quality.compression] as CFDictionary
        )
        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
