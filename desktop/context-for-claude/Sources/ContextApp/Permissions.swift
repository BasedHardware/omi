import AVFoundation
import ContextCore
import AppKit
import CoreGraphics
import Foundation
import Security

/// The three things Context for Claude has to be allowed to do. Nothing else is ever asked for.
enum Capability: String, CaseIterable {
    case microphone
    case systemAudio
    case screen
    case accessibility
}

extension Capability {
    /// The app asks in its own voice, once, in the first person.
    var title: String {
        switch self {
        case .microphone:
            return "I would like to use your microphone, so I can hear what you talk about."
        case .systemAudio:
            return "I would like to hear your calls, so I catch the other side too."
        case .screen:
            return "I would like to see your screen, so I know what you're working on."
        case .accessibility:
            return "I would like to read the text in your windows, so I quote it exactly instead of guessing."
        }
    }

    /// The exact pane to land on, not the top of System Settings — a user who has to hunt for the
    /// row is a user who gives up.
    var settingsPane: String {
        switch self {
        case .microphone:
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        case .systemAudio:
            // **Not the Microphone pane.** This used to send system audio there, on the reasoning
            // that a CoreAudio process tap is consented to as audio capture and that there was "no
            // separate system-audio pane to send anyone to". Measured on macOS 26.5.2 (25F84), that
            // is false in both halves: Privacy & Security ▸ Screen & System Audio Recording carries
            // *two* lists — "Screen & System Audio Recording" and, below it, "System Audio Recording
            // Only" — and the tap's switch is in the second one. The Microphone pane does not list
            // it at all.
            //
            // So the old route opened a pane the row was not on, and the overlay then correctly
            // refused to point at anything. From the user's side that is the same pane opening twice
            // for what looks like one permission: "asking the screen/system audio recording
            // permission multiple times".
            //
            // `PermissionChoreography.sectionOccurrence(for:)` is the other half of this pair — it
            // picks which of the two lists to ring, and it has to say 1 for exactly this reason.
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        case .screen:
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        case .accessibility:
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        }
    }

    /// **Where the switch is, in the words System Settings uses for it.**
    ///
    /// `settingsPane` is for `NSWorkspace`; this is for a sentence the user reads when nothing is
    /// opening the pane for them. System audio names the *list* as well as the pane, because that
    /// pane carries two and the app appears in both — sending someone to the top of it is how the
    /// last round of this bug had people switching on the row they had already switched on.
    var settingsLocation: String {
        switch self {
        case .microphone:
            return "Privacy & Security ▸ Microphone"
        case .systemAudio:
            return "Privacy & Security ▸ Screen & System Audio Recording, under "
                + "“System Audio Recording Only”"
        case .screen:
            return "Privacy & Security ▸ Screen & System Audio Recording"
        case .accessibility:
            return "Privacy & Security ▸ Accessibility"
        }
    }
}

/// What the user thinks they granted.
///
/// macOS splits each of these in two, and neither split is a decision anyone is making. A
/// microphone tap and a system-audio tap are separate TCC records, but "hear me" and "hear the
/// other side of the call" are one idea. Reading a window's text is a separate grant from capturing
/// its pixels, but both are just *seeing the screen* — the tree and the screenshot are two readings
/// of one window, and the app wants them together or the answer is half blind.
///
/// A row per TCC record made the menu bar read like a permissions audit. A row per capability reads
/// like what the app actually does.
enum CapabilityGroup: String, CaseIterable {
    case microphone
    case screen

    /// Ordered: a tap acts on the first member still ungranted, so the row always offers the nearest
    /// piece of work rather than the last one.
    var members: [Capability] {
        switch self {
        case .microphone: return [.microphone, .systemAudio]
        case .screen: return [.screen, .accessibility]
        }
    }

    var title: String {
        switch self {
        case .microphone: return "Microphone"
        case .screen: return "Screen"
        }
    }

    /// The first member still missing, or nil when the whole group is in.
    ///
    /// The one rule this surface cannot break: a group reads "Granted" only when **every** member
    /// is granted. A row that says granted over a half-missing capability is the row lying, and it
    /// is the failure the menu bar can least afford — so the rule is a pure function of the answers,
    /// separable from how they were obtained, and asserted as such.
    func firstMissing(_ granted: (Capability) -> Bool) -> Capability? {
        members.first { !granted($0) }
    }

    func isGranted(_ granted: (Capability) -> Bool) -> Bool {
        firstMissing(granted) == nil
    }
}

enum Permissions {

    // MARK: - Reading

    /// **Every read is also an observation.**
    ///
    /// The answer is unchanged; what the wrapper adds is that the ledger behind `aGrantJustArrived`
    /// is fed by the polls the app already runs rather than by a clock of its own. The engine
    /// re-reads every capability every thirty seconds and the onboarding gate does it twice a
    /// second, so "a grant arrived while we were running" is a fact the app is already in a position
    /// to notice — it simply was not writing it down.
    static func check(_ c: Capability) -> Bool {
        let granted = liveCheck(c)
        grantLedger.observe(c, granted: granted)
        return granted
    }

    private static func liveCheck(_ c: Capability) -> Bool {
        switch c {
        case .microphone:
            return AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
        case .systemAudio:
            return cachedSystemAudioGrant()
        case .screen:
            // Sampling the launch snapshot here is what makes `screenNeedsRelaunch` truthful: it has
            // to be taken before the user can possibly grant anything, and the first capability poll
            // happens at launch.
            _ = screenGrantedAtLaunch
            return screenIsGranted(
                preflight: CGPreflightScreenCaptureAccess(),
                capturedRecently: capturedRecently(.screen))
        case .accessibility:
            return AXElement.isTrusted
        }
    }

    /// One row per capability rather than per TCC record — what the menu bar shows.
    ///
    /// A group is granted only when every member is: a row that reads "granted" while half of it is
    /// still missing would be the row lying, which is the one failure this surface cannot afford.
    /// The status word comes from the first member still waiting, so the row describes the work that
    /// remains rather than the best case.
    ///
    /// `granted` is injectable so the grouping rule can be asserted without live TCC state; nothing
    /// in the app passes it.
    static func groupedReport(granted isGranted: (Capability) -> Bool = { check($0) }) -> [CapabilityReport] {
        CapabilityGroup.allCases.map { group in
            let waiting = group.firstMissing(isGranted)
            let granted = waiting == nil
            // Granted groups still defer to the first member's word, because `screen` reports
            // "action required" while a grant is waiting on a relaunch.
            let subject = waiting ?? group.members[0]
            return CapabilityReport(
                name: group.rawValue,
                granted: granted,
                detail: statusWord(for: subject, granted: granted))
        }
    }

    /// Fixed order — the onboarding rows read this top to bottom.
    static func report() -> [CapabilityReport] {
        let ordered: [Capability] = [.microphone, .systemAudio, .screen, .accessibility]
        return ordered.map { c in
            let granted = check(c)
            return CapabilityReport(name: c.rawValue, granted: granted, detail: statusWord(for: c, granted: granted))
        }
    }

    // MARK: - A grant that arrived while this process was running

    /// **How recently a grant has to have landed for a quit nobody here asked for to be macOS
    /// recycling this process on account of it.**
    ///
    /// Measured on this Mac: the switch is flipped in Privacy & Security at 11:40:09 and the Quit
    /// Apple Event lands at 11:40:11. Two seconds. The window is not that tight because macOS's
    /// alert sits there until it is answered, and a user who reads it before pressing "Quit &
    /// Reopen" is still inside the same episode. It is not much wider either: every second of it is
    /// a second in which an ordinary external quit would be undone instead, and staying quit is the
    /// safe direction for every clause of this decision.
    static let grantArrivalSeconds: Double = 120

    /// **Whether a capability this process could not use has just become one it can.**
    ///
    /// The narrow half of `ContextAppDelegate.shouldReviveAfterTermination`. "Somebody other than
    /// the user ended us" is equally true of an update installing itself — the 13:35 termination in
    /// this app's own log is Sparkle, one second after it launched its updater — and of `killall`,
    /// and reviving either of those is the app refusing to leave. What is true *only* of the TCC
    /// case is that a grant this process was without a moment ago is now in place, which is the
    /// entire reason macOS ends the process: capture rights are settled when a process starts, so
    /// the new answer cannot reach this one.
    ///
    /// Reads every capability before answering rather than trusting the ledger as it stands. The
    /// quit follows the switch by a second or two and the app's own capability poll runs every
    /// thirty, so on the reported timeline nothing had looked since before the grant existed.
    ///
    /// **A grant *lost* is deliberately not this.** macOS raises the same alert when a switch goes
    /// off, and a user who takes a permission away and then ends the app is a user the app must not
    /// argue with.
    static func aGrantJustArrived(
        within seconds: Double = grantArrivalSeconds, now: Double = ContextTime.now
    ) -> Bool {
        readEveryCapability()
        return grantArrivedRecently(
            secondsSince: grantLedger.secondsSinceGrantArrived(now: now), within: seconds)
    }

    /// Seeds the ledger with what this process was allowed to do when it started, so that a change
    /// has something to be a change *from*.
    ///
    /// Called from `applicationDidFinishLaunching`, before any UI exists to grant anything, rather
    /// than left to the launch-time capability poll: `groupedReport` stops at a group's first
    /// ungranted member, so on a Mac with the microphone missing the system-audio row is never read
    /// at launch and its baseline would be taken at whatever later moment something got around to
    /// asking — which is exactly the moment a grant would be invisible from.
    static func noteGrantsAtLaunch() {
        readEveryCapability()
    }

    /// Pure, so the window is assertable without a TCC record moving.
    ///
    /// `>= 0` for the reason `capturedRecently` has it: a clock that moved backwards leaves a stamp
    /// in the future, and a stamp in the future has to read as "nothing just arrived" rather than as
    /// a licence to reopen.
    nonisolated static func grantArrivedRecently(secondsSince: Double?, within: Double) -> Bool {
        guard let secondsSince else { return false }
        return secondsSince >= 0 && secondsSince <= within
    }

    private static func readEveryCapability() {
        for c in Capability.allCases { _ = check(c) }
    }

    // MARK: - Asking

    /// Two-stage, because macOS is two-stage: the first ask raises the system prompt, and every ask
    /// after a denial opens the Settings pane instead — TCC never shows the same prompt twice, so a
    /// second `requestAccess` call would silently do nothing and the row would look broken.
    ///
    /// Every caller goes through `PermissionBroker`, which is what makes "one at a time" a fact
    /// about the app rather than a convention each of the six call sites has to remember.
    @discardableResult
    static func request(_ c: Capability) async -> Bool {
        await PermissionBroker.shared.request(c)
    }

    /// Sends the user to the exact pane. Also brokered: an unserialised open is how a pane the user
    /// was deliberately sent to gets replaced by a different one a second and a half later.
    static func openSettings(for c: Capability) {
        Task { @MainActor in await PermissionBroker.shared.openSettings(for: c) }
    }

    /// Whether the system prompt for this capability has already been spent. macOS shows each one
    /// exactly once, so a caller that sees `true` must open the pane rather than ask again.
    ///
    /// **Accessibility is always spent, because it never had a prompt to spend.** macOS shows no
    /// dialog for it at any point — `request(.accessibility)` opens the pane and nothing else, and
    /// `markPrompted` is consequently only ever called for the three that do prompt. Answering
    /// `false` here meant every caller took the will-prompt branch: the card hid itself and captioned
    /// "macOS is asking. I'll wait." for a dialog that cannot arrive, and then the pane was opened a
    /// second time about two seconds later by the wait that follows. One press, two panes, under a
    /// sentence describing something that never happened — the same defect the screen beat already
    /// documents having fixed on its own path.
    static func promptIsSpent(_ c: Capability) -> Bool {
        promptIsSpent(c, hasPrompted: hasPrompted(c))
    }

    /// The rule itself, split from the machine it reads. `hasPrompted` is a fact about *this* Mac, so
    /// a test written against the live call passes for the wrong reason on a Mac that has already
    /// spent all three prompts — and would go on passing if the rule were replaced by `true`.
    nonisolated static func promptIsSpent(_ c: Capability, hasPrompted: Bool) -> Bool {
        c == .accessibility || hasPrompted
    }

    /// The ask itself, with no exclusion of its own. Only `PermissionBroker` may call it — the door
    /// is the single owner, and a second entrance would restore exactly the defect it exists for.
    fileprivate static func performRequest(_ c: Capability) async -> Bool {
        state.begin(c)
        defer { state.end(c) }

        switch c {
        case .microphone:
            return await requestMicrophone()
        case .systemAudio:
            return await requestSystemAudio()
        case .screen:
            return await requestScreen()
        case .accessibility:
            // There is no prompt to raise. macOS grants Accessibility only through System Settings,
            // by hand, and `AXIsProcessTrustedWithOptions` merely nags with a dialog that leads
            // there — so send the user straight to the row instead of showing a dialog about a
            // dialog. Unlike Screen Recording this takes effect immediately, with no relaunch.
            performOpenSettings(for: c)
            return AXElement.isTrusted
        }
    }

    fileprivate static func performOpenSettings(for c: Capability) {
        guard let url = URL(string: c.settingsPane) else { return }
        // Sending someone to the Screen Recording pane is the last moment this process can still
        // learn anything about that grant, so it is the moment worth remembering. See
        // `screenSettingsWasOpened`.
        if c == .screen { screenSettingsOpened.signal() }
        let open = {
            NSWorkspace.shared.open(url)
            ContextLog.info("Opened the \(c.rawValue) pane in System Settings", "permissions")
        }
        if Thread.isMainThread {
            open()
        } else {
            DispatchQueue.main.async(execute: open)
        }
    }

    /// True while the user is looking at System Settings.
    ///
    /// The onboarding card floats above everything, so it has to step aside while the pane it just
    /// opened is the thing being read — and step back the moment it is not. An `LSUIElement` app has
    /// no Dock icon to click, so a card ordered out with no way back is a dead end; this is what
    /// bounds the hiding to exactly the window in which it is right.
    static var systemSettingsIsFrontmost: Bool {
        NSWorkspace.shared.frontmostApplication?.bundleIdentifier == systemSettingsBundleID
    }

    static let systemSettingsBundleID = "com.apple.systempreferences"

    /// How often anything here re-asks the system for an answer only the user can give.
    ///
    /// Polling is the one timed thing the onboarding flow keeps, and it earns its place by being
    /// *detection* rather than a trigger: macOS posts no notification when a TCC switch is flipped, or
    /// when System Settings comes forward, so asking repeatedly is the only way to notice the user did
    /// something. Nothing downstream of a poll may advance a card or start an action the user did not.
    /// Seconds is the source spelling because `Timer.publish` takes a `TimeInterval` and `Duration`
    /// cannot be handed to it — two literals would be two cadences waiting to drift apart.
    static let grantWatchPollSeconds: TimeInterval = 0.4
    static var grantWatchPoll: Duration { .seconds(grantWatchPollSeconds) }

    /// Waits until System Settings is actually frontmost, so an overlay points at a pane that exists.
    ///
    /// This replaces a flat `Task.sleep(1_200 ms)` at both onboarding call sites. The sleep was a
    /// guess at how long the pane takes to appear and it was wrong in both directions: on a cold
    /// System Settings launch the overlay drew before the pane arrived and ringed the *previous*
    /// pane's rows, and on a warm one it made the user wait more than a second after their own click
    /// for a hint that was already positionable.
    ///
    /// - Parameter timeout: gives up pointing rather than waiting forever — System Settings may be
    ///   refused, or the user may have switched away. Returning on a timeout is safe because every
    ///   caller re-checks what it is about to draw.
    /// - Returns: whether the pane came forward.
    @discardableResult
    static func waitForSettingsFrontmost(timeout: Duration = .seconds(6)) async -> Bool {
        var waited: Duration = .zero
        while waited < timeout {
            if systemSettingsIsFrontmost { return true }
            try? await Task.sleep(for: grantWatchPoll)
            waited += grantWatchPoll
        }
        return systemSettingsIsFrontmost
    }

    // MARK: - Has this ever worked

    /// **Whether this install has ever actually used a capability, as opposed to been offered it.**
    ///
    /// "Never granted" and "was granted, then lost" read identically through TCC — both answer the
    /// preflight with `false` — and they are not remotely the same event. The first is the user's
    /// own choice and deserves a calm sentence. The second is a promise that has stopped being
    /// kept, and on 2 August 2026 it cost a day and a half of screen history: re-signing the bundle
    /// invalidated the Screen Recording grant (TCC keys it to the code signature), the microphone's
    /// grant survived because it is keyed differently, and nothing anywhere noticed the difference.
    ///
    /// **This is not a development-only hazard.** Any update that ships under a changed signing
    /// identity or a changed designated requirement does the same thing to every install in the
    /// field, silently. So the fact is written down the first time a capability genuinely produces
    /// something, and stays written for the life of the install.
    static func hasEverCaptured(_ c: Capability) -> Bool {
        defaults.bool(forKey: Key.everCaptured(c))
    }

    /// Records that `c` has produced real output — just now, and at least once ever. Cheap enough to
    /// call from a capture path: the stamp is one locked dictionary write, and the `UserDefaults`
    /// write behind the guard happens once in the life of the install.
    static func noteCaptureSucceeded(_ c: Capability) {
        captureClock.stamp(c)
        guard !hasEverCaptured(c) else { return }
        defaults.set(true, forKey: Key.everCaptured(c))
        ContextLog.milestone("\(c.rawValue) capture confirmed working on this install", "permissions")
    }

    /// **How recently output has to have landed for it to still be proof.**
    ///
    /// Bounded from below by the capture path's own quietest cadence: `ScreenPipeline`'s force
    /// interval is 60 s, so a window nobody is touching still produces a capture every minute, and
    /// anything shorter than that would call a perfectly healthy screen unproven. Bounded from
    /// above by the other direction — a grant that genuinely dies has to stop being vouched for
    /// while the user is still looking at the menu bar, not minutes later.
    static let captureEvidenceSeconds: Double = 150

    /// Whether `c` has produced something recently enough for that to still describe *now*.
    ///
    /// A clock that has moved backwards (NTP, a wake from sleep) reads as no evidence rather than
    /// as fresh evidence: with nothing observed the preflight is the answer again, which is where
    /// this started and is never worse than it.
    static func capturedRecently(
        _ c: Capability,
        within seconds: Double = captureEvidenceSeconds,
        now: Double = ContextTime.now
    ) -> Bool {
        guard let at = captureClock.lastOutput(c) else { return false }
        let elapsed = now - at
        return elapsed >= 0 && elapsed <= seconds
    }

    /// **Observed capture outranks the preflight, and nothing outranks observed capture.**
    ///
    /// `CGPreflightScreenCaptureAccess` answers a question about TCC's records; the thing anyone
    /// actually wants to know is whether *this* process can capture, and those are different
    /// questions by construction. The window server fixes a process's capture rights when it
    /// connects, so the preflight describes the next launch as often as this one — and it reads
    /// false for a bundle whose signature has just changed, which on a machine that rebuilds the
    /// app all day is most of the time.
    ///
    /// A stream that produced pixels a moment ago has already answered. There is no arrangement of
    /// TCC records that makes a frame on disk not have happened, so evidence is an *or*: it adds an
    /// answer where the preflight had a wrong one, and the preflight keeps its place as the answer
    /// for the case with no evidence at all.
    ///
    /// The inverse is what `captureEvidenceSeconds` bounds. An install that has never captured has
    /// nothing to offer here, and a grant that dies stops producing inside the window. Neither can
    /// be talked into reading "granted".
    static func screenIsGranted(preflight: Bool, capturedRecently: Bool) -> Bool {
        preflight || capturedRecently
    }

    /// True when a capability this install has demonstrably used is no longer granted.
    ///
    /// The one state the product must never meet with silence, and the reason it is a named
    /// predicate rather than an inline `&&`: every surface that reports a missing permission has to
    /// agree on which of the two stories it is telling.
    static func grantWasLost(_ c: Capability) -> Bool {
        hasEverCaptured(c) && !check(c)
    }

    /// **What to do about a grant macOS has dropped and is still drawing as switched on.**
    ///
    /// One sentence, shared by every surface that meets this state, because the previous three
    /// spellings of it were all wrong in the same way: they said *switch it back on*, and there is
    /// nothing to switch back on. Observed on this machine on 15 August 2026, on the shipped
    /// notarized 1.0.4 — the app reported `screen: not granted — Action required`, and the row in
    /// Privacy & Security ▸ Screen & System Audio Recording was **already on**. The system log says
    /// why:
    ///
    /// ```
    /// tccd: Failed to match existing code requirement for subject com.omi.context-for-claude and
    ///       service kTCCServiceMicrophone
    /// ```
    ///
    /// A TCC record carries the code requirement of the binary that earned it. After a re-sign the
    /// requirement no longer matches, so the daemon refuses the app while System Settings goes on
    /// rendering the row from the record it still has. The switch is not the state; it is a picture
    /// of a record that no longer applies to us.
    ///
    /// One remedy that rewrites the record against the new signature — turn it **off** and back on —
    /// and it is the same sentence for microphone, system audio and screen, because all three are one
    /// `tccd` requirement mismatch wearing three different pane names. Telling a user to switch on a
    /// switch they can see is already on is what turned this into *"the app is broken"* rather than
    /// *"the app needs a click"*.
    ///
    /// **But it is no longer the *first* thing said, because it is not the common case.** On 16
    /// August 2026 this text was measured wrong on this Mac, on the shipped notarized 1.0.11: screen
    /// capture was dead, the switch was on, and a plain relaunch restored it — `granted true,
    /// capturing true` — with nothing toggled and no record rewritten. Nothing had been dropped.
    /// `CGPreflightScreenCaptureAccess()` is answered per process, so a stale `false` is
    /// indistinguishable *here* from a revocation, and it is much the more frequent of the two: it
    /// happens on every auto-update, to every install.
    ///
    /// So the cheap, non-destructive remedy leads and the record-rewriting one is the fallback. Both
    /// are still named, and the sentence still refuses to claim the switch is off — that part was
    /// right and stays. Ordering them the other way round sends the majority of readers to re-toggle
    /// a switch that was never the problem.
    nonisolated static func staleGrantReason(subject: String, for c: Capability) -> String {
        "\(subject) has stopped working. Reopening me fixes this most of the time — a grant only "
            + "reaches me when I start, and the switch may still look on. If it comes back after "
            + "that, turn it off and back on in \(c.settingsLocation), then reopen me again."
    }

    /// **Why the screen half cannot run right now, or nil when nothing is in its way.**
    ///
    /// Three distinct situations wear the same checkbox, and telling them apart is most of what a
    /// user needs from this app when the screen goes quiet. One function rather than three
    /// conditions at three call sites, because the engine, the menu bar and the MCP `status` tool
    /// all have to be telling the same story — the previous arrangement had the engine writing one
    /// sentence, the watcher logging a different one, and `status` reporting neither.
    /// **The one spelling of the command that repairs an unusable Screen Recording record.**
    ///
    /// Named here rather than written out at each place that needs it, because there are now two: the
    /// sentence `ScreenBlock.recordUnusable` renders, and the menu bar control that copies it to the
    /// clipboard. A command the user is told to run and a command the app puts on their clipboard have
    /// to be the same string — two literals is how they drift, and a wrong bundle id in a `tccutil`
    /// line either does nothing or resets somebody else's permission.
    ///
    /// Names the *running* bundle, not the one that ships. A dev build handing the user
    /// `tccutil reset ScreenCapture com.omi.context-for-claude` tells them to destroy the production
    /// app's grant, which repairs nothing here and breaks something that was working.
    static let screenRecordResetCommand = screenRecordResetCommand(for: ContextPaths.bundleIdentifier)

    static func screenRecordResetCommand(for bundleIdentifier: String) -> String {
        "tccutil reset ScreenCapture \(bundleIdentifier)"
    }

    enum ScreenBlock: Equatable {
        /// Never granted. The user's own choice, and nothing has gone wrong.
        case notGranted
        /// Granted once, used, and now gone. macOS drops a Screen Recording grant when the code
        /// signature it was keyed to changes — a re-sign, or an update shipped under a different
        /// identity — and it does so without a word to anybody.
        case grantLost
        /// The grant is real and this process cannot use it. Window-server capture rights are fixed
        /// when a process connects, so a grant made after launch applies to the *next* launch. This
        /// is the one case no amount of polling can fix.
        case needsRelaunch
        /// The grant is switched on, this process started *holding* it, and macOS refused it anyway.
        /// The record itself is unusable and only deleting it will help — see
        /// `screenGrantStaleness(grantedAtLaunch:captureDeclined:)`.
        case recordUnusable

        var reason: String {
            switch self {
            case .notGranted:
                return "Screen off — Screen Recording permission not granted"
            case .grantLost:
                return staleGrantReason(subject: "Screen Recording", for: .screen)
            case .needsRelaunch:
                // Deliberately does not assert that the switch is on. This state is now also reached
                // when the preflight is merely per-process stale (see `screenNeedsRelaunch`), where
                // whether the user actually flipped it is the one thing this process cannot know —
                // and a sentence that tells someone their switch is on when it is off is how the
                // previous rounds of this bug read to the people hitting them.
                return "Screen Recording only reaches me when I start, so it has to be reopened "
                    + "before I can see the screen. If you've just switched it on, click the "
                    + "Screen row to restart me."
            case .recordUnusable:
                // Names the command because the command is the only thing that works. Every softer
                // sentence this app has tried here — "reopen me", "turn it off and back on" — is a
                // loop the user cannot get out of, and they have been round it: *"Granting screen
                // permissions doesn't work. I've already granted permissions."*
                return "Screen Recording is on and macOS still refuses me — the permission was "
                    + "recorded by an earlier version of me, and reopening cannot replace it. In "
                    + "Terminal: \(Permissions.screenRecordResetCommand). Then grant it once more."
            }
        }

        /// Whether this is something that was working and is not. Drives the log level, because an
        /// `info` line is evicted from the unified log within minutes and this is precisely the
        /// event that has to still be there tomorrow.
        ///
        /// `.recordUnusable` counts for the same reason `.grantLost` does, and rather more: it is a
        /// state the user cannot leave without being told a command, so the line explaining it is
        /// the one a support conversation a day later has to be able to find.
        var isRegression: Bool { self == .grantLost || self == .recordUnusable }
    }

    static func screenBlock() -> ScreenBlock? {
        screenBlock(
            granted: check(.screen),
            hasEverCaptured: hasEverCaptured(.screen),
            needsRelaunch: screenNeedsRelaunch,
            recordIsUnusable: screenRecordIsUnusable)
    }

    /// **The trichotomy itself, as a pure function of the three facts it is made of.**
    ///
    /// Separated from the machine because every input is something only this Mac can answer — a TCC
    /// record, a `UserDefaults` flag, a window-server refusal — while the *rule* is where the wrong
    /// answer lives. The wrong answer it had was `nil`, returned over a process that could not
    /// capture at all, and `nil` is not a status: it is a licence for `ScreenWatcher` to ask the
    /// WindowServer again every three seconds, forever. Each of those asks is a TCC request, and
    /// macOS answers a request it will not honour by putting *"Context for Claude would like to
    /// record this computer's screen and audio"* on screen — which is the reported bug, arriving on
    /// a loop over a switch the user can see is already on.
    nonisolated static func screenBlock(
        granted: Bool, hasEverCaptured: Bool, needsRelaunch: Bool, recordIsUnusable: Bool
    ) -> ScreenBlock? {
        guard granted else { return hasEverCaptured ? .grantLost : .notGranted }
        // Ahead of `needsRelaunch`, and it has to be: an unusable record is *also* a stale grant, so
        // both flags are true at once and whichever is tested first is the sentence the user reads.
        // Testing the relaunch first is how this app spent two rounds telling a user to reopen it
        // for a record no reopening can repair.
        if recordIsUnusable { return .recordUnusable }
        return needsRelaunch ? .needsRelaunch : nil
    }

    // MARK: - Screen Recording relaunch

    /// Screen Recording only takes effect after a relaunch — the UI has to say so rather than
    /// leaving the user staring at a granted checkbox and a dead capture.
    ///
    /// The window server decides what a process may capture when that process connects, so a grant
    /// made while Context for Claude is running applies to the *next* Context for Claude, never this one.
    static var screenNeedsRelaunch: Bool {
        guard CGPreflightScreenCaptureAccess() else {
            // **A false preflight is not the same claim as "not granted", and treating it as one is
            // what made this state unreachable in exactly the case it exists for.**
            //
            // `CGPreflightScreenCaptureAccess()` is answered per *process*: a grant made after we
            // connected to the window server reads `false` here for the rest of our life, however
            // many times we ask. Measured on this Mac on 16 August 2026, on the shipped notarized
            // 1.0.11, with the switch visibly ON in Privacy & Security ▸ Screen & System Audio
            // Recording: the running process reported `screen: granted false`, and a relaunch — with
            // nothing else touched, no toggling, no `tccutil` — reported `granted true, capturing
            // true`. The record was never in question; only this process's view of it was.
            //
            // So the old `return false` here was the bug behind *"Permission is already on but it's
            // still asking for it"*: it made this the one branch that could never fire once the user
            // had done the thing it was written to notice.
            //
            // Once we have sent someone to that pane, `false` stops being evidence of anything. The
            // honest answer is the reopen, and it is safe to offer for two reasons that have to hold
            // together. `screenSettingsWasOpened` dies with the process, so a successor starts from a
            // fresh preflight rather than an inherited suspicion. And every surface that acts on this
            // bounds the acting: `PermissionDeadEnd.mayRelaunch` spends one reopen and no more, which
            // is what stops a user who never granted from being restarted on a loop.
            //
            // The persisted flag is still cleared, and still should be: it records a grant this
            // process *watched* arrive, which is precisely what has not happened here.
            defaults.set(false, forKey: Key.screenPendingRelaunch)
            return screenRelaunchOfferWhenPreflightDenies(settingsWasOpened: screenSettingsWasOpened)
        }
        if screenGrantIsStale(
            grantedAtLaunch: screenGrantedAtLaunch,
            captureDeclined: screenCaptureWasDeclined)
        {
            // Persisted so the nudge survives a crash before the user gets around to reopening.
            defaults.set(true, forKey: Key.screenPendingRelaunch)
        }
        return defaults.bool(forKey: Key.screenPendingRelaunch)
    }

    /// **Whether a grant TCC vouches for is one this process cannot actually use.**
    ///
    /// Two independent proofs, and the second one is the whole of this fix.
    ///
    /// `!grantedAtLaunch` is the case this predicate was written for: the grant appeared *after* we
    /// connected to the window server, so it belongs to the next launch. It is also the only case it
    /// could ever detect, and it is the wrong half of the problem. A bundle re-signed under a new
    /// identity — this app's move from an ad-hoc build to a notarized Developer ID one — is granted
    /// **before** the process starts: `CGPreflightScreenCaptureAccess()` reads `true` at launch, so
    /// `screenGrantedAtLaunch` is `true`, so nothing ever armed the nudge, so `screenBlock()`
    /// answered "nothing is in your way" to a process ScreenCaptureKit was refusing outright. The
    /// state this whole predicate exists to name was unreachable in exactly the situation that
    /// produces it.
    ///
    /// `captureDeclined` closes that: it is ScreenCaptureKit itself answering `userDeclined`, which
    /// is macOS saying the grant does not apply to *this* process. That is not a thing to retry —
    /// window-server capture rights are settled when a process connects — and retrying is what put
    /// the system alert on a three-second loop in front of a user whose switch was already on.
    nonisolated static func screenGrantIsStale(grantedAtLaunch: Bool, captureDeclined: Bool) -> Bool {
        screenGrantStaleness(grantedAtLaunch: grantedAtLaunch, captureDeclined: captureDeclined) != .none
    }

    /// **Which of the two stale states this is — and they are not the same problem.**
    ///
    /// `screenGrantIsStale` above answers "is the grant TCC vouches for unusable by this process",
    /// and that was the right question for its own fix. It is the wrong question to *act* on,
    /// because its two disjuncts have opposite remedies and it hands back one boolean:
    ///
    /// - **`!grantedAtLaunch`** — the grant appeared after we connected to the window server. Those
    ///   rights are settled at connection time, so the grant belongs to the *next* process. A
    ///   reopen genuinely fixes this, and the app should offer one.
    /// - **`grantedAtLaunch && captureDeclined`** — this process started already holding the grant,
    ///   and macOS refused it anyway. There is nothing here for a reopen to change: the next
    ///   process will start holding exactly the same grant and be refused for exactly the same
    ///   reason. Something about the *record* is wrong, not about this process's timing.
    ///
    /// The second state is the reported bug, and this Mac's own logs are what name it. `tccd`,
    /// still firing while this was written:
    ///
    /// ```text
    /// tccd: Failed to match existing code requirement for subject com.omi.context-for-claude
    ///       and service kTCCServiceScreenCapture
    ///         identifier "com.omi.context-for-claude" and certificate leaf = H"bb925114bcb6…"
    ///         identifier "com.omi.context-for-claude" and anchor apple generic and certificate
    ///           1[field.1.2.840.113635.100.6.2.6] … and certificate leaf[subject.OU] = "9536L8KLMP"
    /// ```
    ///
    /// Two requirements: the one TCC **stored** when the grant was first given, pinned to the leaf
    /// certificate of a build signed with a different key, and the one this Developer ID build
    /// actually has. TCC matches against the stored blob, and flipping the switch in System Settings
    /// updates the row's allowed flag without rewriting it — so the grant is permanently inert and
    /// every remedy the app has offered so far is a dead end the user loops on. Verbatim: *"Granting
    /// screen permissions doesn't work. I've already granted permissions."*
    ///
    /// **What makes this detectable without reading TCC's database** — which is SIP-protected, and
    /// so is the log that carries the line above — is that a relaunch is a *control*. `grantedAtLaunch`
    /// is the app's own record of whether the grant was already there when this process started, and
    /// `captureDeclined` is ScreenCaptureKit's `userDeclined` on this process. True together, they
    /// say the reopen this app asks for has already been performed and changed nothing. From the
    /// live trace of the report, that is exactly the pair, twice, in two consecutive processes:
    ///
    /// ```text
    /// 11:39:56  Context for Claude[9394]  ScreenCaptureKit refused this process while TCC still
    ///                                     reports the grant as on
    /// 11:42:13  Context for Claude[9660]  ScreenCaptureKit refused this process while TCC still
    ///                                     reports the grant as on
    /// ```
    ///
    /// **What was rejected, and why**, since both alternatives look reasonable until they are
    /// measured:
    ///
    /// - *Compare a stored cdhash against this build's*, the way `reconcileSystemAudioRecords`
    ///   already does for its own cached grant. Measured on the affected install:
    ///   `context.permission.systemAudio.signature` is `708e9a67…` and the installed bundle's
    ///   `CDHash` is `708e9a67…` — the same. The re-sign that poisoned the TCC record happened
    ///   *before* that key was ever written, so the comparison reports "unchanged" for precisely the
    ///   install that has the problem. It can only ever catch a *future* re-sign, which is no help
    ///   to anybody already stuck.
    /// - *Count the launches that met a lost grant.* It cannot separate "the record is unusable"
    ///   from "the user switched it off and has not switched it back on", so it would tell people to
    ///   delete a permission they revoked deliberately.
    ///
    /// Both are guesses about history. This is an observation about now, and it needs nothing
    /// persisted at all.
    enum ScreenGrantStaleness: Equatable {
        /// The grant is real and this process is using it.
        case none
        /// The grant belongs to the next process. Reopening is the remedy.
        case waitingOnRelaunch
        /// The grant is unusable no matter how many processes ask. Deleting the record is the remedy.
        case recordUnusable
    }

    nonisolated static func screenGrantStaleness(
        grantedAtLaunch: Bool, captureDeclined: Bool
    ) -> ScreenGrantStaleness {
        // The grant arrived mid-run, so the next process is the one that gets it — whether or not
        // ScreenCaptureKit has got round to refusing this one yet.
        guard grantedAtLaunch else { return .waitingOnRelaunch }
        // Held since launch. A refusal now cannot be about this process being early.
        return captureDeclined ? .recordUnusable : .none
    }

    /// The live reading of the state above: this process launched holding the grant and macOS
    /// refused it anyway.
    ///
    /// Both inputs are process-scoped on purpose and neither is persisted, which is what makes this
    /// self-limiting: a successor that is not refused reports `false` on its own, with nothing to
    /// clear and no stale flag to outlive the problem.
    static var screenRecordIsUnusable: Bool {
        screenGrantStaleness(
            grantedAtLaunch: screenGrantedAtLaunch, captureDeclined: screenCaptureWasDeclined)
            == .recordUnusable
    }

    /// **Records that ScreenCaptureKit refused this process, in so many words.**
    ///
    /// Called from the one place that can know — the capture path, on `SCStreamError.userDeclined` —
    /// and it is the observation that turns an unbounded retry into a single attempt: from the next
    /// tick on, `screenBlock()` reports `.needsRelaunch`, the watcher stands down instead of asking
    /// again, and the menu bar offers the relaunch that is the only thing that can actually fix it.
    ///
    /// `milestone` rather than `info`, because `info` is evicted from the unified log within minutes
    /// and this is the line that explains why the screen half went quiet.
    static func noteScreenCaptureDeclined() {
        guard !screenCaptureDeclined.isSignalled else { return }
        screenCaptureDeclined.signal()
        // Which of the two refusals this is, at the moment it happens. The same sentence for both
        // is how the log from the reported incident reads as "reopen me" twice in two consecutive
        // processes without ever saying that the reopen had already been tried.
        ContextLog.milestone(
            "ScreenCaptureKit refused this process while TCC still reports the grant as on — "
                + (screenRecordIsUnusable
                    ? "and this process launched already holding the grant, so no reopening can "
                        + "fix it: the TCC record itself is unusable"
                    : "Context for Claude has to be reopened before it can see the screen"),
            "permissions")
    }

    /// Whether this process has already been refused. Read by `screenNeedsRelaunch`, and by the
    /// capture path so it never spends a second refused request.
    static var screenCaptureWasDeclined: Bool { screenCaptureDeclined.isSignalled }

    /// **Arranges for this bundle to be reopened once this process is gone, and returns.**
    ///
    /// The order is the whole fix. This used to ask `NSWorkspace` to launch a second instance of our
    /// own bundle with `createsNewApplicationInstance`, pump the runloop until the launch callback
    /// fired, and only then `exit(0)`. Reported verbatim: *"when I did quit and reopen, it does not
    /// quit and reopen on its own … the app does not reopen, which it should."*
    ///
    /// The callback is not the signal it was being read as. `openApplication` calls back when
    /// LaunchServices has **accepted the request**, not when the replacement is running, so `exit(0)`
    /// raced a process that had barely started. Worse, the two instances overlap by construction: a
    /// second copy of a bundle that is already running is exactly the case LaunchServices may
    /// coalesce back onto the instance already registered — the one about to call `exit(0)`. The
    /// launch "succeeded" and the app was gone.
    ///
    /// So nothing here launches anything. A detached `/bin/sh` waits for this pid to leave the
    /// process table and *then* opens the bundle, by which time there is no instance to coalesce
    /// onto and `open` does the ordinary single-instance launch. The child is reparented to `launchd`
    /// when we die, so our exit cannot take it with us — the one property the old shape could never
    /// have, because whatever relaunches us has to outlive us.
    ///
    /// `kill -0` is a liveness test, not a signal: it asks whether the pid still exists and delivers
    /// nothing. The 200-iteration ceiling is a leak guard — if this process somehow never dies, the
    /// helper gives up after ~20 s rather than sitting in the process table forever.
    ///
    /// **This is deliberately separate from `relaunchApp()`.** Two paths need it and they differ in
    /// exactly one respect: who ends the process. Our own "Restart to finish" button ends it itself
    /// (`relaunchApp`); a termination macOS started ends it for us, and the delegate only gets to
    /// leave a helper behind on the way out (`ContextAppDelegate.applicationWillTerminate`). The
    /// shell script is the part that must not be written twice.
    ///
    /// - Returns: whether the helper is running. A caller about to `exit(0)` on the strength of it
    ///   has to know; a caller already being terminated has nothing to decide.
    @discardableResult
    static func spawnRelaunchHelper() -> Bool {
        let url = Bundle.main.bundleURL
        // Single-quoted and escaped: the bundle name contains spaces ("Context for Claude.app") and
        // the install location is the user's to choose.
        let quoted = "'" + url.path.replacingOccurrences(of: "'", with: "'\\''") + "'"
        let pid = ProcessInfo.processInfo.processIdentifier
        let script = """
            i=0
            while kill -0 \(pid) 2>/dev/null && [ $i -lt 200 ]; do
              sleep 0.1
              i=$((i+1))
            done
            exec /usr/bin/open \(quoted)
            """

        let relauncher = Process()
        relauncher.executableURL = URL(fileURLWithPath: "/bin/sh")
        relauncher.arguments = ["-c", script]
        do {
            try relauncher.run()
            // `milestone`: the helper outlives this process, so its pid is the only handle anyone
            // has on "did the relaunch actually get arranged" — and `info` is evicted from the log
            // within minutes, which is how the last failure came to have no trace at all.
            ContextLog.milestone(
                "Relaunch helper \(relauncher.processIdentifier) will reopen \(url.lastPathComponent)",
                "permissions")
            return true
        } catch {
            ContextLog.error("Relaunch helper failed to spawn: \(error.localizedDescription)", "permissions")
            return false
        }
    }

    /// Quits this process and starts a fresh one, **in that order**. The button behind
    /// "Restart to finish".
    ///
    /// **This used to end the process with `exit(0)`, and that was wrong in a way nothing could
    /// see.** `exit(0)` does not run `applicationWillTerminate`, so this path — the one the app puts
    /// in front of a user the moment they grant Screen Recording — skipped `Engine.pause()`
    /// entirely. That callback is what closes the open capture session and writes the final
    /// heartbeat, and its own note says what happens without it: *"the last session stays open
    /// forever and `status()` reports a recording that stopped hours ago."* Every restart from this
    /// button left one behind. It also skipped the `Termination —` milestone, which is why a
    /// restart is the one way of leaving this app that leaves no trace in the log at all.
    ///
    /// `NSApp.terminate` runs the delegate this app already has, so the flush has one owner rather
    /// than a second copy here — the same argument that keeps the relauncher script in
    /// `spawnRelaunchHelper()` and nowhere else. The origin is marked first because the delegate
    /// asks *who ended this run*: unmarked, a restart pressed seconds after a grant landed is
    /// precisely the shape `shouldReviveAfterTermination` revives, and the app would spawn a second
    /// relaunch helper on top of the one this function has already arranged.
    ///
    /// **The order is still the whole fix, and it is unchanged.** The helper goes up before
    /// anything ends the process, and the process only ends if the helper is genuinely running —
    /// `Process.run()` throws when the spawn fails, so `true` means a real pid exists. What no
    /// caller can verify is the `open` at the far end of it, because by then there is nothing left
    /// to verify it with; that is inherent to an app relaunching itself, and the milestone the
    /// helper logs is the handle the next report has on it.
    ///
    /// Still `-> Never`, and still honest: the two paths that do not terminate park the thread
    /// rather than return. Parking runs the run loop rather than blocking it, so AppKit is free to
    /// process the termination that was just asked for — and if it somehow never arrives, the user
    /// is left with a running app instead of no app, which is the direction this whole function has
    /// to fail in.
    static func relaunchApp() -> Never {
        guard prepareRelaunch() else { park() }

        // Both call sites are a click — the menu bar's Screen row and onboarding's "Restart to
        // finish" — so this is the main thread by construction.
        MainActor.assumeIsolated {
            TerminationOrigin.relaunchWasArrangedHere()
            NSApp.terminate(nil)
        }
        park()
    }

    /// **Everything a restart does before the point of no return**, and whether the process may now
    /// be ended.
    ///
    /// Split out because the two lines after it cannot be run by a test without ending the test
    /// process, and the decision they are gated on is the one with a user-visible wrong answer:
    /// ending a process whose replacement was never arranged leaves somebody who pressed "Restart
    /// to finish" with no app at all. `spawnHelper` is injectable for that reason and nothing in the
    /// app passes it.
    ///
    /// - Returns: `false` when the helper did not come up, which the caller must read as *stay
    ///   running*. The card is still on screen and the menu bar still offers Quit, so a failed
    ///   restart costs the user a click rather than their app.
    static func prepareRelaunch(spawnHelper: () -> Bool = { spawnRelaunchHelper() }) -> Bool {
        guard spawnHelper() else {
            ContextTelemetry.recordFallback(
                area: .settings, from: "relaunch", to: "stay-running",
                reason: "helper-spawn-failed", outcome: .degraded)
            return false
        }
        return true
    }

    /// Runs the run loop forever, for the two paths of `relaunchApp()` that must not return.
    ///
    /// Deliberately not `sleep` or a bare spin: AppKit still has to be able to process the
    /// termination this was called after, and the app still has to answer its menu bar if that
    /// termination never comes.
    private static func park() -> Never {
        while true { RunLoop.current.run(mode: .default, before: .distantFuture) }
    }

    // MARK: - Per-capability request paths

    private static func requestMicrophone() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return true
        case .notDetermined:
            markPrompted(.microphone)
            let granted = await AVCaptureDevice.requestAccess(for: .audio)
            ContextLog.info("Microphone prompt answered: \(granted ? "granted" : "denied")", "permissions")
            return granted
        default:
            // Determined and denied. The prompt will never appear again, so the pane is the only
            // route left.
            performOpenSettings(for: .microphone)
            return false
        }
    }

    /// Whether an ask should raise the system prompt, or fall back to the Settings pane.
    ///
    /// The prompted latch exists because `CGRequestScreenCaptureAccess` returns false immediately
    /// once an answer is on record, so asking twice makes the row feel dead. But the latch is
    /// permanent, and a grant can go away after it is set: a changed signing identity drops it, and
    /// on macOS 26 screen-recording approval lapses on its own by design. In that state the latch
    /// sends every ask to a Settings pane the app may not even be listed in, so the user toggles
    /// something that never takes and capture stays dead forever.
    ///
    /// A grant this install demonstrably had, now missing, is a *fresh* ask rather than a repeat.
    static func screenAskShouldPrompt(hasPrompted: Bool, grantWasLost: Bool) -> Bool {
        !hasPrompted || grantWasLost
    }

    private static func requestScreen() async -> Bool {
        if CGPreflightScreenCaptureAccess() { return true }

        guard screenAskShouldPrompt(hasPrompted: hasPrompted(.screen), grantWasLost: grantWasLost(.screen)) else {
            // `CGRequestScreenCaptureAccess` returns false immediately once the answer is on record;
            // calling it again would make the row feel dead.
            performOpenSettings(for: .screen)
            return false
        }

        markPrompted(.screen)
        // Blocking, and it puts a modal dialog up — never on the main thread.
        let granted = await offMain { CGRequestScreenCaptureAccess() }
        if screenNeedsRelaunch {
            ContextLog.info("Screen recording granted; capture stays dead until Context for Claude is reopened", "permissions")
        }
        return granted || CGPreflightScreenCaptureAccess()
    }

    private static func requestSystemAudio() async -> Bool {
        if cachedSystemAudioGrant() { return true }

        let firstAsk = !hasPrompted(.systemAudio)
        if firstAsk { markPrompted(.systemAudio) }

        let granted = await probeSystemAudio()
        if !granted && !firstAsk {
            // The consent dialog fired on an earlier ask and macOS will not repeat it, so the second
            // tap has to land the user on the switch itself.
            performOpenSettings(for: .systemAudio)
        }
        return granted
    }

    // MARK: - System audio: the capability with no preflight
    //
    // CoreAudio process taps have no `AVCaptureDevice.authorizationStatus` equivalent — the only way
    // to learn the answer is to build a tap and see whether it comes back. Building one is not free
    // and the *first* one raises the TCC prompt, so a naive poll would both cost real work every
    // second and re-prompt the user throughout onboarding. Hence the cache: the answer is written to
    // `UserDefaults` and served from there, and a stale answer is refreshed at most once every 30
    // seconds, off the polling thread.

    /// The slow cadence: how stale a background answer may get before another tap is worth building.
    static let systemAudioProbeInterval: Double = 30

    /// **Whether the background poll should spend a CoreAudio tap on re-asking.**
    ///
    /// A pure function, and separate from the read that uses it, because every input is a fact this
    /// process cannot make up on demand — a `UserDefaults` pair and a TCC prompt record — and the
    /// rule they combine into is the one with a wrong answer available. It is asserted directly
    /// rather than through a read with a side effect on a HAL that has to be talked to.
    ///
    /// - `cached == true` never re-probes: a grant is trusted for the life of the process, because a
    ///   second global tap while capture is live is the one thing that can knock the live tap over.
    /// - `cached == nil` **does**, and that is the fix. "Never probed" was previously answered `false`
    ///   with no probe scheduled, forever — the state a machine is in before its first tap, and the
    ///   one state that could never recover on its own.
    /// - `prompted == false` never probes, whatever else is true. The first tap raises the TCC
    ///   consent dialog, and raising it from a poll is precisely the surprise the click-driven card
    ///   exists to remove. Once the user has clicked the row, macOS has spent that prompt.
    static func systemAudioProbeIsDue(cached: Bool?, prompted: Bool, secondsSinceProbe: Double) -> Bool {
        guard cached != true, prompted else { return false }
        return secondsSinceProbe > systemAudioProbeInterval
    }

    /// **Whether a *read* may spend a CoreAudio tap of its own** — the rule the background poll
    /// actually runs on, and the one `systemAudioProbeIsDue` above is only half of.
    ///
    /// `prompted` was being answered from `context.permission.systemAudio.prompted`, a `UserDefaults`
    /// flag, and that is the whole defect. The flag is durable; the thing it claims — that macOS has
    /// already spent this app's audio-capture consent dialog — is a fact about a TCC record keyed to a
    /// code signature, and TCC drops that record without a word whenever the signature changes or the
    /// grant is reset (`tccutil reset AudioCapture`, measured; and an approval that lapses on its own
    /// on macOS 26). The flag then vouches for a prompt that has *not* been spent, so the poll builds
    /// a global process tap, and macOS answers a tap with no record by putting the consent dialog on
    /// screen. Every 30 seconds. Forever. Started by nothing the user did — `Permissions.check` is a
    /// read, and the onboarding card and the menu bar both call it on a timer.
    ///
    /// That is the same shape as the Screen Recording loop and the keychain loop: a refusal no retry
    /// can satisfy, retried on a clock. The fix is the same shape too — the only evidence that this
    /// process cannot raise a dialog is that this process has *already* had a tap answered, which is
    /// a fact about the run rather than a record that outlives it.
    ///
    /// So an unattended probe stays behind a latch signalled by `probeSystemAudio()`, and every
    /// caller of that is a click: the row's ask, the pane-opening that materialises the row, and the
    /// gate's own fast refresh while the user stands in System Settings. Before the user has clicked
    /// anything, a read is a read.
    ///
    /// What this costs is a launch in which the user granted system audio elsewhere and never touches
    /// the row: the cached answer is served until they click it once. That is a stale word next to a
    /// switch, against an unrequested system dialog on a loop, and it is not a close call.
    nonisolated static func unattendedProbeIsDue(
        cached: Bool?, tapAnsweredInThisProcess: Bool, secondsSinceProbe: Double
    ) -> Bool {
        guard tapAnsweredInThisProcess else { return false }
        return systemAudioProbeIsDue(cached: cached, prompted: true, secondsSinceProbe: secondsSinceProbe)
    }

    /// **A tap macOS has refused outranks the record that says we may have one.**
    ///
    /// The system-audio mirror of `screenIsGranted(preflight:capturedRecently:)`, and it points the
    /// other way for the same reason that one points the way it does: evidence beats a record. There
    /// is no preflight for a process tap, so `check(.systemAudio)` answers from `UserDefaults`, and
    /// `reconcileSystemAudioRecords` only falsifies that cache **at launch**, per signature. Nothing
    /// falsified it *within* a run — so a grant revoked while the app was capturing left the menu bar
    /// reading "Granted" and the onboarding card counting the row answered, over a tap CoreAudio was
    /// refusing, until the next launch.
    ///
    /// `nil` is preserved rather than collapsed to `false`: never-probed is the state the row reports
    /// as "Open", and a refusal is not a reason to claim we asked.
    nonisolated static func systemAudioIsGranted(cached: Bool?, tapRefused: Bool) -> Bool? {
        tapRefused ? false : cached
    }

    /// **Records that CoreAudio refused this process a tap, in so many words.**
    ///
    /// The system-audio counterpart of `noteScreenCaptureDeclined`, called from the one boundary that
    /// can know — `SystemAudioCapture`, on a tap creation the HAL turned down — and deliberately in
    /// memory only. What it holds is a fact about *this* run: a tap is built fresh every time, so a
    /// refusal carried into the next launch would condemn a process that may well get one, and the
    /// persisted answer is already reconciled per signature at launch.
    ///
    /// `milestone` rather than `info`, because `info` is evicted from the unified log within minutes
    /// and this is the line that explains why the call half went quiet mid-session.
    static func noteSystemAudioTapRefused() {
        guard !systemAudioTapRefused.isSignalled else { return }
        systemAudioTapRefused.signal()
        ContextLog.milestone(
            "CoreAudio refused this process a system-audio tap while the recorded answer still said "
                + "granted — the consent has to be re-given before calls can be heard",
            "permissions")
    }

    /// Whether a tap has been refused in this run and not yet succeeded since. Read by
    /// `cachedSystemAudioGrant`, which is what every other read comes through.
    static var systemAudioTapWasRefused: Bool { systemAudioTapRefused.isSignalled }

    /// The last answer we got from an actual tap, and the schedule that stops it going stale.
    ///
    /// **The condition for re-probing is "we do not have a grant", not "we have a recorded denial".**
    /// It used to return at the first `guard` whenever the key was absent, which is the state a
    /// machine that has never run a tap is in — so the one case that could *never* recover on its own
    /// was the fresh one. The card polls `check` every 1.5 s, `check` came here, and here answered
    /// `false` forever without ever asking CoreAudio a single question. A user who flipped the switch
    /// in System Settings watched the row keep saying it was missing, which is the reported *"even
    /// after I turned it on this still doesnt go away"* with the episode already over.
    ///
    /// A grant, by contrast, is still trusted for the life of the process: a second global tap while
    /// capture is live is the one thing that can knock the live tap over.
    ///
    /// `hasPrompted` is what keeps this inside the card's own rule — **nothing is asked until the
    /// user asks**. The first tap raises the TCC consent dialog, and raising it from a background
    /// poll would be exactly the surprise `PermissionInvitations` exists to remove; after the user
    /// has clicked the row once, macOS has spent that prompt and a probe is silent.
    private static func cachedSystemAudioGrant() -> Bool {
        // Before the cache is read, not after: a cached answer written under a signature this build
        // no longer has is not an answer about this build. Once per process, like
        // `screenGrantedAtLaunch`, and forced from the first read for the same reason.
        _ = systemAudioRecordsReconciled

        // Every other read of the grant — `check`, the three ask paths' first guard, the status word
        // — comes through here, so this is the one place the refusal has to be applied. Applied to
        // the value the probe schedule sees as well: a refused answer is a `false` answer, and the
        // recovery it licenses is the click-driven probe that notices the switch being re-flipped.
        let cached = systemAudioIsGranted(
            cached: defaults.object(forKey: Key.systemAudioGranted) as? Bool,
            tapRefused: systemAudioTapRefused.isSignalled)
        if unattendedProbeIsDue(
            cached: cached,
            tapAnsweredInThisProcess: systemAudioTapAnswered.isSignalled,
            secondsSinceProbe: ContextTime.now - defaults.double(forKey: Key.systemAudioProbedAt))
        {
            scheduleSystemAudioProbe()
        }
        // Never probed and never asked for — unknown, reported as "Open" rather than guessed at.
        return cached ?? false
    }

    /// Re-asks CoreAudio, now, instead of waiting for the 30 s staleness window.
    ///
    /// System audio is the one capability with no preflight: a grant made in System Settings is
    /// invisible to this process until another tap is built. A watch that only polls `check` would
    /// therefore wait forever on a switch the user has already flipped, so the watcher refreshes
    /// explicitly rather than relying on a read with a side effect.
    ///
    /// **Two cadences, and what separates them is whether the user is looking at the switch.** This
    /// is the fast one and it is only reached from `PermissionGate`'s unbounded watch: the user is
    /// standing in System Settings with our arrow on the row, so the flip has to register while they
    /// are still looking at it. The slow one is `systemAudioProbeInterval` — 30 s — which is what an
    /// idle card and the menu bar pay for the same fact.
    ///
    /// Neither is the overlay tracker's 40 ms tick, deliberately. A probe is a real CoreAudio tap,
    /// built and torn down behind `systemAudioProbeLock`, and rebuilding one at tick rate would both
    /// serialise the watch behind the HAL and keep re-creating a global tap under a user who may be
    /// in a call. Two seconds against the watch's 500 ms poll is at most one probe every four polls.
    static func refreshSystemAudioGrant(minimumInterval: Double = 2) async {
        guard !cachedSystemAudioGrant() else { return }
        guard ContextTime.now - defaults.double(forKey: Key.systemAudioProbedAt) >= minimumInterval
        else { return }
        _ = await probeSystemAudio()
    }

    /// **Attempts the thing the row governs, before anybody is sent to look for the row.**
    ///
    /// macOS creates the "System Audio Recording Only" TCC record **lazily** — on a CoreAudio process
    /// tap the application attempts, not when it is installed and not when the pane is opened.
    /// Measured on macOS 26.5.2 (25F84): `tccutil reset AudioCapture com.omi.context-for-claude`
    /// **removed** our row from that list, reproducing the reported screenshot exactly — this app in
    /// the upper list and switched on, the lower list holding one other application and nothing of
    /// ours. A tap attempt by the app put the row back, twice, and it then survived quitting the app.
    /// System Settings does not always redraw the list at once, so the row can take a minute or two
    /// to become visible even after the record exists; nothing here waits for that.
    ///
    /// The more useful half is that **the attempt is itself the answer.** Both times, immediately
    /// after that reset, the tap came back and `check(.systemAudio)` was true — no dialog, nothing
    /// for the user to do, and the pane never needed at all. Opening System Settings first turned a
    /// permission that was already available into a window, an arrow and a row to hunt for; and when
    /// the row genuinely was not drawn yet, there was nothing in that list to point at. Attempting
    /// the tap first collapses both into one step.
    ///
    /// `PermissionRun` is why this cannot live inside the ask: it skips `request` outright once
    /// `promptIsSpent`, which is every run after the first, so from the second run onwards nothing in
    /// the episode ever tried the tap again.
    ///
    /// Only system audio needs this — every other capability is listed as soon as macOS knows the app
    /// exists — so it is a no-op for the rest rather than a per-capability branch at the call site.
    static func materialiseSettingsRow(for c: Capability) async {
        guard c == .systemAudio, !cachedSystemAudioGrant() else { return }
        _ = await probeSystemAudio()
    }

    private static func scheduleSystemAudioProbe() {
        guard state.beginIfIdle(.systemAudio) else { return }
        // Stamp before the work so a burst of polls cannot queue a second probe behind this one.
        defaults.set(ContextTime.now, forKey: Key.systemAudioProbedAt)
        // Through the door like every other privileged acquisition. A background probe is a real
        // CoreAudio tap, and one built while a TCC dialog is on screen is the same class of
        // collision as a second dialog — observed live as `System audio stalled` mid-run.
        Task { @MainActor in
            let granted = await PermissionBroker.shared.hold(.systemAudio) {
                await offMain { primeSystemAudioTap() }
            }
            recordSystemAudio(granted)
            state.end(.systemAudio)
        }
    }

    private static func probeSystemAudio() async -> Bool {
        defaults.set(ContextTime.now, forKey: Key.systemAudioProbedAt)
        let granted = await offMain { primeSystemAudioTap() }
        // **The one thing that licenses a background probe.** Every caller of this function is a
        // click, so a tap has now been attempted with the user present and macOS has an answer on
        // record for *this* process — which is the only state in which a later, unattended tap is
        // guaranteed not to raise a dialog nobody asked for.
        systemAudioTapAnswered.signal()
        recordSystemAudio(granted)
        return granted
    }

    // MARK: - System audio: records that must not outlive the signature that earned them

    /// **Whether persisted system-audio answers written under `stored` still describe a build
    /// signed as `current`.**
    ///
    /// System audio is the one capability with no preflight, so `check` answers it from
    /// `UserDefaults` — and that cache is the only capability answer in the app that nothing can
    /// falsify. `refreshSystemAudioGrant`, `materialiseSettingsRow` and `requestSystemAudio` all
    /// return at their first guard once it reads `true`, so a `true` written by a previous build is
    /// permanent: `check(.systemAudio)` says granted, the menu bar's Microphone row ANDs it in and
    /// reads "Granted", the onboarding card counts it answered and never offers it, and the capture
    /// path is the only thing that ever finds out — as an opaque device error, with no route to the
    /// switch.
    ///
    /// That is not a hypothetical. Measured on this machine on 15 August 2026, having just installed
    /// the notarized 1.0.4 over an ad-hoc-signed build: `context.permission.systemAudio.granted = 1`,
    /// written under a signature macOS has since dropped the TCC record for. Every existing install
    /// that updates across a signing-identity change arrives in exactly this state.
    ///
    /// TCC keys its records to the code signature, so this scopes ours the same way. Two deliberate
    /// asymmetries, both toward keeping less:
    ///
    /// - **An absent stamp does not survive.** A build that predates this reconciliation wrote
    ///   answers under an unknown signature, and 1.0.4 is precisely that build. Costing a user one
    ///   click on a row is the whole downside; the alternative is the paragraph above.
    /// - **An unknown *current* signature changes nothing.** If `SecCode` cannot answer, the honest
    ///   move is to leave the records alone rather than to spend them on a guess.
    nonisolated static func systemAudioRecordsSurvive(stored: String?, current: String?) -> Bool {
        guard current != nil else { return true }
        guard let stored else { return false }
        return stored == current
    }

    /// Spends every persisted system-audio answer that a different build wrote, and stamps this one.
    ///
    /// Takes its `defaults` and its `signature` rather than reading both, because the interesting
    /// behaviour is the mutation — which keys go, which stay, and that a second call with the same
    /// signature is a no-op — and none of that is assertable against a live keychain-signed bundle
    /// and the real standard domain.
    ///
    /// - Returns: whether records were spent.
    @discardableResult
    nonisolated static func reconcileSystemAudioRecords(defaults: UserDefaults, signature: String?) -> Bool {
        let stored = defaults.string(forKey: Key.systemAudioSignature)
        guard !systemAudioRecordsSurvive(stored: stored, current: signature) else { return false }
        guard let signature else { return false }
        // The prompt record goes with the grant. It claims macOS has spent this app's consent
        // dialog, which is the same claim about the same dropped TCC record — and left behind it
        // would send the row's first click down the "the prompt is spent, open the pane" branch for
        // a prompt that is about to appear.
        defaults.removeObject(forKey: Key.systemAudioGranted)
        defaults.removeObject(forKey: Key.systemAudioProbedAt)
        defaults.removeObject(forKey: Key.prompted(.systemAudio))
        defaults.set(signature, forKey: Key.systemAudioSignature)
        // `milestone`: this is the line that explains why a user who had system audio working was
        // asked for it again, and `info` is evicted from the unified log within minutes.
        ContextLog.milestone(
            "System audio consent was recorded under a different code signature — the answer has "
                + "been dropped and will be asked for again",
            "permissions")
        return true
    }

    /// Runs the reconciliation once, on the live records.
    private static let systemAudioRecordsReconciled: Void = {
        reconcileSystemAudioRecords(defaults: .standard, signature: codeSignature)
    }()

    /// **This bundle's code signature, in the same terms TCC keys a grant to.**
    ///
    /// The cdhash rather than the team identifier, because an ad-hoc-signed build has no team and
    /// two consecutive ad-hoc builds are exactly the pair between which a grant disappears. It is
    /// stable across launches of a shipped build, so nothing in the field pays for it twice.
    private static let codeSignature: String? = {
        var code: SecCode?
        guard SecCodeCopySelf([], &code) == errSecSuccess, let code else { return nil }
        var staticCode: SecStaticCode?
        guard SecCodeCopyStaticCode(code, [], &staticCode) == errSecSuccess, let staticCode else { return nil }
        var information: CFDictionary?
        guard SecCodeCopySigningInformation(staticCode, [], &information) == errSecSuccess,
            let unique = (information as? [String: Any])?[kSecCodeInfoUnique as String] as? Data
        else { return nil }
        return unique.map { String(format: "%02x", $0) }.joined()
    }()

    private static let systemAudioProbeLock = NSLock()

    /// Builds and tears down one tap. Two overlapping global taps is exactly the state CoreAudio
    /// refuses, so probes stay single-file — an unlucky overlap would cache a denial that is not one.
    private static func primeSystemAudioTap() -> Bool {
        systemAudioProbeLock.lock()
        defer { systemAudioProbeLock.unlock() }
        return SystemAudioCapture.primePermission()
    }

    private static func recordSystemAudio(_ granted: Bool) {
        let previous = defaults.object(forKey: Key.systemAudioGranted) as? Bool
        defaults.set(granted, forKey: Key.systemAudioGranted)
        // A tap that came back is the end of the refusal, and the only thing that can be: the latch
        // is what makes `check` disagree with the record, so nothing else could ever clear it and the
        // row would stay dead for the life of the process after one refusal.
        if granted { systemAudioTapRefused.clear() }
        if previous != granted {
            ContextLog.info("System audio consent is now \(granted ? "granted" : "denied")", "permissions")
        }
    }

    // MARK: - Status words

    /// The four words the permission row can show, per `docs/design-system.md`.
    private enum Word {
        /// Shared with `ContextCore` rather than spelled twice: `CaptureState` writes this same word
        /// when it reconciles a report against a live stream, and two spellings of one status are
        /// two claims a reader has to work out are the same claim.
        static let granted = CapabilityReport.grantedDetail
        static let open = "Open"
        static let checking = "Checking"
        static let actionRequired = "Action required"
    }

    private static func statusWord(for c: Capability, granted: Bool) -> String {
        if state.isPending(c) { return Word.checking }

        if granted {
            // A granted screen checkbox over a dead capture is the one state that lies. Say the
            // truth: there is still something for the user to do.
            if c == .screen, screenNeedsRelaunch { return Word.actionRequired }
            return Word.granted
        }

        switch c {
        case .microphone:
            return AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined
                ? Word.open : Word.actionRequired
        case .systemAudio:
            return defaults.object(forKey: Key.systemAudioGranted) == nil ? Word.open : Word.actionRequired
        case .screen:
            return hasPrompted(.screen) ? Word.actionRequired : Word.open
        case .accessibility:
            // Always the same word, because there is no prompt whose absence could mean "not asked
            // yet": the only path to this grant is the Settings row, so the action is identical
            // whether or not the user has been sent there before.
            return Word.actionRequired
        }
    }

    // MARK: - Prompt bookkeeping

    /// Whether the system prompt for this capability has ever been raised. macOS shows each one
    /// exactly once, so this is what turns the second tap on a row into "open Settings".
    private static func hasPrompted(_ c: Capability) -> Bool {
        defaults.bool(forKey: Key.prompted(c))
    }

    private static func markPrompted(_ c: Capability) {
        defaults.set(true, forKey: Key.prompted(c))
    }

    // MARK: - Storage

    private static var defaults: UserDefaults { .standard }

    private enum Key {
        static let systemAudioGranted = "context.permission.systemAudio.granted"
        static let systemAudioProbedAt = "context.permission.systemAudio.probedAt"
        /// The code signature the two records above were written under. See
        /// `Permissions.systemAudioRecordsSurvive(stored:current:)`.
        static let systemAudioSignature = "context.permission.systemAudio.signature"
        static let screenPendingRelaunch = "context.permission.screen.pendingRelaunch"

        static func prompted(_ c: Capability) -> String {
            "context.permission.\(c.rawValue).prompted"
        }

        static func everCaptured(_ c: Capability) -> String {
            "context.capture.\(c.rawValue).everWorked"
        }
    }

    /// Whether this process already had Screen Recording when it connected to the window server.
    /// Lazy, so it is sampled the first time anything asks — which is the launch-time capability
    /// poll, before any UI exists to grant anything.
    private static let screenGrantedAtLaunch: Bool = {
        let granted = CGPreflightScreenCaptureAccess()
        if granted {
            // This process can capture right now, so any pending nudge from the session that earned
            // the grant is spent.
            UserDefaults.standard.set(false, forKey: Key.screenPendingRelaunch)
        }
        return granted
    }()

    // MARK: - Plumbing

    private static let state = RequestState()

    /// In memory and never persisted, because what it holds is a claim about *this* process: a grant
    /// that arrived after we started is precisely the grant a successor launches already holding, so
    /// a stamp carried across a relaunch would tell the successor to relaunch itself for a change it
    /// has already picked up. That is the fork bomb `RevivalBudget` exists to bound, and it should
    /// not be relying on the budget to do it.
    private static let grantLedger = GrantLedger()

    /// In memory on purpose, and never persisted. What it holds is proof about *this* process —
    /// window-server capture rights are fixed when a process connects — so a stamp carried across a
    /// relaunch would be vouching for a process that no longer exists. `hasEverCaptured` is the
    /// durable half, and it answers a different question.
    private static let captureClock = CaptureClock()

    /// In memory and never persisted, for the same reason `captureClock` is not: window-server
    /// capture rights are settled when a process connects, so a refusal is a fact about *this*
    /// process. Carried into the next launch it would condemn a process that may capture perfectly
    /// well — and the next launch is precisely the one the nudge is asking for.
    private static let screenCaptureDeclined = Latch()

    /// Whether *this process* has already sent the user to the Screen Recording pane.
    ///
    /// In memory and never persisted, and that is the whole of what makes the relaunch offer it
    /// unlocks safe to make. See `screenSettingsWasOpened` for what it is for; the reason it must not
    /// outlive the process is that a successor reads a *fresh* preflight, so an offer armed by this
    /// process would otherwise be re-armed forever by a user who never switched anything on.
    private static let screenSettingsOpened = Latch()

    /// Whether this process has sent the user to the Screen Recording pane and can therefore no
    /// longer tell them anything truthful about that grant on its own.
    static var screenSettingsWasOpened: Bool { screenSettingsOpened.isSignalled }

    /// **The rule `screenNeedsRelaunch` applies when the preflight says no — as a pure function.**
    ///
    /// Split out for the same reason `screenBlock(granted:hasEverCaptured:needsRelaunch:
    /// recordIsUnusable:)` is split from `screenBlock()`: every input is something only this Mac can
    /// answer, while the *rule* is where the wrong answer lived. The wrong answer was a flat `false`,
    /// which made the reopen offer unreachable in precisely the situation it exists for.
    ///
    /// Named for the branch it belongs to rather than taking the preflight as a parameter: a `true`
    /// preflight never reaches here — that path has the persisted flag and the staleness check to
    /// work with, and can legitimately answer `false`. A version of this that accepted `preflight`
    /// would have to pin a value for an input it never receives, and the pinned value would
    /// contradict the real rule the moment anyone called it unconditionally.
    ///
    /// So this is only the case where macOS has told this process "no" and that "no" carries no
    /// information, because the answer is fixed per process at window-server connect time.
    nonisolated static func screenRelaunchOfferWhenPreflightDenies(settingsWasOpened: Bool) -> Bool {
        // Nothing has been asked of the user yet, so a refusal is just a refusal: the row should read
        // as an offer to grant, not as an instruction to reopen something that would change nothing.
        settingsWasOpened
    }

    /// Whether *this process* has already had a CoreAudio tap answered, and therefore whether an
    /// unattended one can still surprise the user with a consent dialog. In memory and never
    /// persisted, for the reason the persisted version of this claim was the bug — see
    /// `unattendedProbeIsDue`.
    private static let systemAudioTapAnswered = Latch()

    /// Whether CoreAudio has refused this process a tap since the last one succeeded. In memory and
    /// never persisted, for the reason `screenCaptureDeclined` is not: a tap is built fresh on every
    /// attempt, so a refusal describes this run and nothing beyond it. The one latch here that is
    /// cleared, and `recordSystemAudio` is the only thing that may — see `noteSystemAudioTapRefused`.
    private static let systemAudioTapRefused = Latch()

    private static func offMain<T: Sendable>(_ work: @escaping @Sendable () -> T) async -> T {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning: work())
            }
        }
    }
}

// MARK: - Asking one at a time

/// Everything the sequencer needs from `Permissions`, so the sequence itself can be exercised with
/// no TCC involved.
///
/// The sequence is the part with a wrong answer available — the wrong order, two dialogs at once, a
/// refusal that stalls the rest of the run — and every one of those is a bug a user meets on their
/// first thirty seconds with the app. It is not testable through the static `Permissions` API, so
/// this protocol exists purely as the seam.
@MainActor
protocol PermissionAsking {
    func isGranted(_ capability: Capability) -> Bool
    /// Raises the system prompt, or opens the pane when TCC will not prompt again.
    func request(_ capability: Capability) async -> Bool
    /// True once macOS has spent this capability's prompt. TCC shows each one exactly once, so a
    /// caller that sees `true` must open the pane instead of asking again — a second `requestAccess`
    /// silently does nothing and the row looks dead.
    func promptIsSpent(_ capability: Capability) -> Bool
    /// Sends the user to the exact pane. Separate from `request` so the route out of a denial is
    /// observable rather than buried inside the ask.
    func openSettings(for capability: Capability)
    /// Re-asks the system for a capability whose grant this process cannot otherwise notice.
    /// Only system audio has one; everything else answers from a preflight.
    func refresh(_ capability: Capability) async
    /// Makes this capability's row in System Settings **exist**, for the one capability whose row
    /// macOS only creates once the app has tried the thing it governs. Called before the pane is
    /// opened, so nobody is ever sent to hunt for a row that is not drawn yet.
    func materialiseSettingsRow(for capability: Capability) async
    /// True when the Screen Recording grant is real but this process cannot use it until it is
    /// relaunched. Never a reason to keep waiting: the grant is already the user's answer.
    var screenNeedsRelaunch: Bool { get }
}

/// `PermissionAsking` on the real `Permissions`.
@MainActor
struct LivePermissionAsking: PermissionAsking {
    func isGranted(_ capability: Capability) -> Bool { Permissions.check(capability) }
    func request(_ capability: Capability) async -> Bool { await Permissions.request(capability) }
    func promptIsSpent(_ capability: Capability) -> Bool { Permissions.promptIsSpent(capability) }
    func openSettings(for capability: Capability) { Permissions.openSettings(for: capability) }

    func refresh(_ capability: Capability) async {
        guard capability == .systemAudio else { return }
        await Permissions.refreshSystemAudioGrant()
    }

    func materialiseSettingsRow(for capability: Capability) async {
        await Permissions.materialiseSettingsRow(for: capability)
    }

    var screenNeedsRelaunch: Bool { Permissions.screenNeedsRelaunch }
}

extension PermissionAsking {
    /// **Three of the four capabilities are already listed**, so doing nothing is the correct
    /// behaviour rather than an omission — macOS lists an application under Microphone, Screen
    /// Recording and Accessibility as soon as it knows it exists. Defaulted so a test double that has
    /// nothing to say about the lazily-created row does not have to say it, and so the one capability
    /// that *does* need work says so in one place (`Permissions.materialiseSettingsRow(for:)`).
    func materialiseSettingsRow(for capability: Capability) async {}
}

// MARK: - One door

/// The single door onto every consent surface macOS has.
///
/// `Permissions.request` and `Permissions.openSettings` used to be ownerless statics with six
/// unserialised callers — the onboarding run, a row tap on the card, the by-hand choreography, the
/// `.done` screen button, the menu-bar row, and the tutorial. The only exclusion that existed was
/// *per capability*, and it explicitly permitted different capabilities to proceed at once. Live
/// first-run trace: the user tapped the Screen row and landed on Screen & System Audio Recording;
/// 1.9 seconds later the app opened the Accessibility pane in the same System Settings window,
/// replacing the pane they had just been sent to, and drew a ring over it.
///
/// So the exclusion is cross-capability and it lives here, not at the call sites. Re-entrant for the
/// capability already holding the door, because one episode legitimately prompts *and* opens a pane
/// for the same thing; anything else queues.
@MainActor
final class PermissionBroker {
    static let shared = PermissionBroker()

    /// The capability the door is currently open for, or nil when nothing is in flight.
    private(set) var holder: Capability?
    private var depth = 0
    private var waiting: [CheckedContinuation<Void, Never>] = []

    /// True while any ask or pane is in flight. Drives row `.disabled` on every surface.
    var isBusy: Bool { holder != nil }

    /// Runs `body` with the door held for `capability`. Never two capabilities at once, anywhere.
    func hold<T>(_ capability: Capability, _ body: () async -> T) async -> T {
        await acquire(capability)
        defer { release() }
        return await body()
    }

    func request(_ capability: Capability) async -> Bool {
        await hold(capability) { await Permissions.performRequest(capability) }
    }

    func openSettings(for capability: Capability) async {
        await hold(capability) { Permissions.performOpenSettings(for: capability) }
    }

    private func acquire(_ capability: Capability) async {
        while let holder, holder != capability {
            await withCheckedContinuation { waiting.append($0) }
        }
        holder = capability
        depth += 1
    }

    private func release() {
        depth -= 1
        guard depth == 0 else { return }
        holder = nil
        guard !waiting.isEmpty else { return }
        waiting.removeFirst().resume()
    }
}

/// Asks for a list of capabilities **one at a time**, with air around each ask.
///
/// This is a deliberate earlier fix, extracted rather than rewritten. macOS shows one TCC alert at a
/// time, and firing three concurrently stacks dialogs the user answers blind — they consent to a
/// queue rather than to three separate things. So:
///
/// - The row lights up **alone** for `leadIn` before its dialog opens, long enough to read the
///   sentence it is asking about and short enough that nobody wonders whether the button worked.
/// - After the answer, the new checkmark sits alone for `afterGrant` before the next dialog covers
///   it. A confirmation the user cannot witness is the same as no confirmation.
/// It paces and asks. It does **not** decide the answer: a run that finishes is not a step that may
/// advance, and nothing here has a deadline that could stand in for a user. `PermissionGate` owns
/// the waiting, and its watch is unbounded.
@MainActor
struct PermissionRun {
    /// How long a row is lit before its dialog opens.
    nonisolated static let leadIn: Duration = .milliseconds(900)
    /// How long the answer sits alone before the next dialog opens over it. Also the window in which
    /// TCC finishes writing a grant it has already accepted — a check taken the instant `request`
    /// returns can still read false, and the row would flash "action required" over a permission the
    /// user just gave.
    nonisolated static let afterGrant: Duration = .milliseconds(1_100)

    let asking: any PermissionAsking
    var leadIn: Duration = PermissionRun.leadIn
    var afterGrant: Duration = PermissionRun.afterGrant

    /// What the view needs to know as the run moves.
    struct Callbacks {
        /// The row is lit and nothing is covering it yet.
        var willAsk: (Capability) -> Void = { _ in }
        /// The lead-in is over and the dialog is about to open. This, and only this, is the moment
        /// the card should step aside — hiding on `willAsk` spends the entire lead-in behind an
        /// ordered-out window, which is the whole point of the lead-in.
        var willPrompt: (Capability) -> Void = { _ in }
        /// The answer is in and has been read back. `granted` is what the system reports now, not
        /// what the dialog returned.
        var didAnswer: (Capability, Bool) -> Void = { _, _ in }
    }

    /// Runs `order`, skipping anything already granted. Returns the capabilities that ended granted.
    @discardableResult
    func run(_ order: [Capability], callbacks: Callbacks = Callbacks()) async -> Set<Capability> {
        var landed: Set<Capability> = []
        for capability in order {
            if asking.isGranted(capability) {
                landed.insert(capability)
                continue
            }

            callbacks.willAsk(capability)
            try? await Task.sleep(for: leadIn)

            // macOS shows each prompt exactly once. Asking again does nothing at all, so a spent
            // prompt is not asked a second time — the pane is the only route left, and opening it
            // belongs to whoever owns the waiting, not to the pacer.
            if !asking.promptIsSpent(capability) {
                callbacks.willPrompt(capability)
                _ = await asking.request(capability)
            }
            let granted = asking.isGranted(capability)
            if granted { landed.insert(capability) }
            callbacks.didAnswer(capability, granted)

            try? await Task.sleep(for: afterGrant)
        }
        return landed
    }
}

// MARK: - The gate

/// The permissions step, as a value the view renders rather than a decision the view makes.
///
/// The bug this exists for: leaving the permissions card consulted no grant at all. Both exits
/// called `advance()` unconditionally — one of them under a comment reading "Move on anyway" — and
/// the run's 2 s settle deadline *structurally cannot* observe a Screen Recording grant, because
/// `CGRequestScreenCaptureAccess()` returns before the user has answered. The live first-run trace
/// has the deadline expiring at 10:13:13 and the user opening the pane at 10:13:46; the app was in
/// the tutorial by 10:14:09 with Screen Recording never granted and nothing said about it.
///
/// **The exit predicate is `canLeaveStep`, and nothing else may decide it.** It is true only when
/// every required capability has a terminal, *user-authored* answer: granted, or postponed because
/// the user pressed "I'll do this later". No timeout advances anything.
///
/// A literal "permission or you cannot proceed" is unimplementable on macOS and would be a trap:
/// TCC prompts exactly once, after a Deny only System Settings remains, and a user who simply
/// refuses would be stranded forever. `postpone` is the escape, and it is deliberate, named, and
/// never automatic.
@MainActor
final class PermissionGate: ObservableObject {

    /// Where the run is, which is also what the card is allowed to show and whether it may be on
    /// screen at all.
    enum Phase: Equatable {
        case idle
        /// The row is lit alone and the card is being read. No dialog yet.
        case explaining(Capability)
        /// A TCC dialog is genuinely up.
        case prompting(Capability)
        /// The prompt is spent or was declined; the pane is open and the watch is unbounded.
        case waitingInSettings(Capability)
        /// The grant landed and the confirmation is being witnessed.
        case confirming(Capability)
        /// The run ended with something still unanswered. Only reachable by cancellation.
        case blocked
        /// Every required capability has an answer.
        case complete
    }

    /// The two terminal answers. Both are the user's; neither is a clock's.
    enum Answer: Equatable { case granted, deferred }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var answers: [Capability: Answer] = [:]

    /// How often the unbounded watch re-asks the system. Two beats a second is fast enough that a
    /// flipped switch feels instant and slow enough to cost nothing.
    nonisolated static let watchPoll: Duration = .milliseconds(500)

    let required: [Capability]

    private let asking: any PermissionAsking
    private let broker: PermissionBroker
    private let pacing: PermissionRun
    private let watchPoll: Duration
    private var openedSettings: Set<Capability> = []
    private var isRunning = false

    /// Everything defaults to the live path. The arguments are optional rather than defaulted to
    /// main-actor values because a default expression is evaluated in a nonisolated context.
    init(
        asking: (any PermissionAsking)? = nil,
        required: [Capability] = [.microphone, .systemAudio, .screen],
        broker: PermissionBroker? = nil,
        leadIn: Duration? = nil,
        afterGrant: Duration? = nil,
        watchPoll: Duration? = nil
    ) {
        let asking = asking ?? LivePermissionAsking()
        self.asking = asking
        self.required = required
        self.broker = broker ?? .shared
        self.pacing = PermissionRun(
            asking: asking,
            leadIn: leadIn ?? PermissionRun.leadIn,
            afterGrant: afterGrant ?? PermissionRun.afterGrant)
        self.watchPoll = watchPoll ?? PermissionGate.watchPoll
    }

    /// **The single exit predicate.** Every required capability answered, by the user.
    var canLeaveStep: Bool { required.allSatisfy { answers[$0] != nil } }

    /// True while an episode owns the screen — the rows must not be tappable under it.
    var isBusy: Bool { isRunning }

    /// The capability the card is currently about, if any.
    var subject: Capability? {
        switch phase {
        case .explaining(let c), .prompting(let c), .waitingInSettings(let c), .confirming(let c):
            return c
        case .idle, .blocked, .complete:
            return nil
        }
    }

    /// Whether the card should take itself off screen.
    ///
    /// `prompting` is unconditional: a system dialog is up and the card is in the way. `waiting in
    /// settings` is conditional on the user actually being in System Settings, and that condition is
    /// load-bearing — this app is `LSUIElement`, so a card ordered out has no Dock icon to bring it
    /// back, and a permanently hidden card is exactly the dead end the postpone escape exists to
    /// prevent. `explaining` and `confirming` keep the card **on screen**: they are the lead-in and
    /// the confirmation beat, and hiding through them is what made the preamble unreadable.
    ///
    /// The rule is right; what was wrong is the freshness of `settingsIsFrontmost`. See the poll in
    /// `OnboardingView` — the card floating over the Screen Recording pane was this predicate being
    /// fed a stale `false`, not this predicate being too narrow.
    nonisolated static func cardYields(to phase: Phase, settingsIsFrontmost: Bool) -> Bool {
        switch phase {
        case .prompting: return true
        case .waitingInSettings: return settingsIsFrontmost
        case .idle, .explaining, .confirming, .blocked, .complete: return false
        }
    }

    /// **Which capability the spotlight over System Settings is for, if any.**
    ///
    /// This is the wiring whose absence was the whole of the "no spotlight was drawn" defect, and it
    /// is a pure function of the phase for exactly that reason. The overlay was reachable from two
    /// places — the by-hand offer, which is only ever Accessibility, and the finale, which only runs
    /// at `step == .done` — and from neither of them during `waitingInSettings`, which is the phase
    /// the card is in for **microphone, system audio and screen recording**. So the card said "System
    /// Settings is open on the right row", System Settings *was* open on the right row, and nothing
    /// pointed at it. Nothing failed; nothing was ever asked.
    ///
    /// Only `waitingInSettings` points, and each exclusion is a case where pointing would be wrong
    /// rather than merely absent:
    ///
    /// - `prompting` — a TCC dialog is up. The thing to answer is the dialog, and System Settings may
    ///   not even be open.
    /// - `explaining` — the lead-in, deliberately before the pane is opened. There is nothing there.
    /// - `confirming` — the grant landed. `PermissionOverlay.confirmGranted` owns that beat; a fresh
    ///   `show` would replace the confirmation with an arrow at a switch already flipped.
    nonisolated static func spotlightSubject(of phase: Phase) -> Capability? {
        switch phase {
        case .waitingInSettings(let capability): return capability
        case .idle, .explaining, .prompting, .confirming, .blocked, .complete: return nil
        }
    }

    /// What the card says right now.
    var caption: String? {
        switch phase {
        case .idle, .complete:
            return nil
        case .explaining:
            // There is no "next one" any more: a gate now runs a single capability, started by the
            // user clicking that row. Promising a queue would describe sequencing the card no longer
            // does — and the whole point of the click-driven model is that nothing is queued at you.
            return "I’ll ask macOS for this one, and wait for your answer."
        case .prompting:
            return "macOS is asking. I’ll wait."
        case .waitingInSettings(let capability):
            return Self.waitingCaption(for: capability)
        case .confirming(let capability):
            if capability == .screen, asking.screenNeedsRelaunch {
                return "Granted. I’ll need to be reopened before I can actually see the screen."
            }
            return "Got it."
        case .blocked:
            return "Still waiting on an answer."
        }
    }

    /// **What the card says while the pane is open — and the one capability it must say it to
    /// differently.**
    ///
    /// `static` so the sentence can be measured without standing a gate up in a phase; it is a pure
    /// function of the capability, and the thing worth guarding about it is the wording.
    ///
    /// Screen Recording gets its own sentence because the shared one makes a promise macOS does not
    /// allow us to keep. "Switch it on and I'll notice" is true for microphone and system audio, and
    /// false for this one: window-server capture rights are fixed when a process connects, so the
    /// switch the user is looking at reaches the **next** Context for Claude, never this one. Saying
    /// otherwise is what left the reporter watching a row read "Asking…" over a switch they could
    /// see was already on — so this sentence names the reopen instead of promising a poll.
    nonisolated static func waitingCaption(for capability: Capability) -> String {
        if capability == .screen {
            return """
                System Settings is open on the right row. Switch it on, then click this row to \
                reopen me — macOS only hands screen access to me when I start, so I can’t pick it \
                up while I’m running. If now is not the time, tell me and I’ll ask again later. \
                \(waitingDetail(for: capability))
                """
        }
        return """
            System Settings is open on the right row. Switch it on and I’ll notice — I won’t move \
            on without an answer. If now is not the time, tell me and I’ll ask again later. \
            \(waitingDetail(for: capability))
            """
    }

    nonisolated private static func waitingDetail(for capability: Capability) -> String {
        switch capability {
        case .microphone: return "It’s under Privacy & Security ▸ Microphone."
        // Named for the list it is really in, not just the pane. That pane carries two, and sending
        // someone to the top of it leaves them switching on the row they already switched on.
        case .systemAudio:
            return "It’s under Privacy & Security ▸ Screen & System Audio Recording, in the "
                + "“System Audio Recording Only” list."
        case .screen: return "It’s under Privacy & Security ▸ Screen & System Audio Recording."
        case .accessibility: return "It’s under Privacy & Security ▸ Accessibility."
        }
    }

    // MARK: Running

    /// Walks the required capabilities, one episode at a time. Returns when every one of them has an
    /// answer, or when the task is cancelled.
    func run() async {
        guard !isRunning else { return }
        isRunning = true
        defer {
            isRunning = false
            phase = canLeaveStep ? .complete : .blocked
        }

        for capability in required {
            guard answers[capability] == nil else { continue }
            guard !Task.isCancelled else { return }
            await episode(for: capability)
        }
    }

    /// The escape, and the only thing other than a grant that ends an episode.
    ///
    /// Deliberately not a default, not a timeout, and not a quiet Continue: the user pressed a button
    /// that says what it does. Everything still works without the capability, worse — which is what
    /// the card says next to the button.
    func postpone(_ capability: Capability) {
        guard answers[capability] == nil else { return }
        answers[capability] = .deferred
        ContextLog.info("\(capability.rawValue) postponed by the user", "permissions")
        if !isRunning { phase = canLeaveStep ? .complete : .blocked }
    }

    private func episode(for capability: Capability) async {
        if asking.isGranted(capability) {
            answers[capability] = .granted
            return
        }

        await broker.hold(capability) {
            phase = .explaining(capability)
            await pacing.run(
                [capability],
                callbacks: .init(
                    willPrompt: { [weak self] in self?.phase = .prompting($0) },
                    didAnswer: { [weak self] capability, granted in
                        // Either way the card comes back: the confirmation has to be witnessed, and
                        // a refusal has to be met with the route out rather than a hidden window.
                        self?.phase = granted ? .confirming(capability) : .explaining(capability)
                    }))

            if asking.isGranted(capability) {
                answers[capability] = .granted
                return
            }
            guard answers[capability] == nil else { return }

            await waitInSettings(for: capability)
        }
    }

    /// The unbounded watch. There is no deadline here on purpose: the 2 s one it replaces expired
    /// 33 seconds before the user in the live trace so much as opened the pane.
    private func waitInSettings(for capability: Capability) async {
        phase = .waitingInSettings(capability)
        if openedSettings.insert(capability).inserted {
            // **The row first, then the pane.** System audio's row in "System Audio Recording Only"
            // does not exist until this app has attempted a CoreAudio process tap — macOS creates the
            // record lazily — so opening the pane before attempting one sends the user to a list they
            // are not in, and points an overlay at a row that is not drawn. See
            // `Permissions.materialiseSettingsRow(for:)` for the measurement.
            await asking.materialiseSettingsRow(for: capability)
            guard !Task.isCancelled else { return }
            // The attempt is itself an answer for system audio: an application that already holds the
            // consent gets its tap, and there is then nothing in System Settings to do. Ending here
            // rather than opening the pane anyway is what keeps this one step instead of a pane that
            // opens and is immediately made pointless.
            if asking.isGranted(capability) {
                answers[capability] = .granted
                phase = .confirming(capability)
                try? await Task.sleep(for: pacing.afterGrant)
                return
            }
            asking.openSettings(for: capability)
        }

        while answers[capability] == nil, !Task.isCancelled {
            try? await Task.sleep(for: watchPoll)
            guard !Task.isCancelled else { return }
            await asking.refresh(capability)
            guard asking.isGranted(capability) else { continue }
            answers[capability] = .granted
            phase = .confirming(capability)
            try? await Task.sleep(for: pacing.afterGrant)
            return
        }
    }
}

/// Which capabilities have an ask in flight. The menu bar polls `report()` on the main thread while
/// a row tap runs `request` off it, so this is shared state and needs the lock.
private final class RequestState: @unchecked Sendable {
    private let lock = NSLock()
    private var pending: Set<Capability> = []

    func begin(_ c: Capability) {
        lock.lock()
        pending.insert(c)
        lock.unlock()
    }

    /// True only for the caller that won the race — used to keep background probes single-file.
    func beginIfIdle(_ c: Capability) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return pending.insert(c).inserted
    }

    func end(_ c: Capability) {
        lock.lock()
        pending.remove(c)
        lock.unlock()
    }

    func isPending(_ c: Capability) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return pending.contains(c)
    }
}

/// **When a capability this process could not use last became one it can.**
///
/// Not `private`, unlike the three below it, and that is deliberate: this is the seam the revival
/// rule is asserted through. Every input to `Permissions.aGrantJustArrived()` other than this is a
/// live TCC record, so a test written against the static API can only ever assert whatever this Mac
/// happens to be granted — and would go on passing if the transition rules here were replaced by
/// `true`.
///
/// The rules, and why each one is a rule:
///
/// - **A first sighting is a baseline, not a change.** There is nothing before it for it to differ
///   from, and counting it would make every launch of an app that is granted everything look like a
///   grant that had just landed.
/// - **Only a transition *into* granted is stamped.** macOS raises its "Quit & Reopen" alert when a
///   switch goes off as well as on, and an app that reopens itself after the user revokes a
///   permission is the app arguing with them.
/// - **A grant that has been in place for hours is not one that just arrived.** The stamp moves on
///   the transition and not on the readings that follow it, so the thirty-second poll cannot keep
///   renewing it — otherwise every external quit for the rest of the session would be undone.
///
/// Locked for the reason `CaptureClock` is: written from whichever thread happened to read a
/// capability, and read from the delegate on the way out.
final class GrantLedger: @unchecked Sendable {
    private let lock = NSLock()
    private var seen: [Capability: Bool] = [:]
    private var arrivedAt: Double?

    func observe(_ c: Capability, granted: Bool, now: Double = ContextTime.now) {
        lock.lock()
        defer { lock.unlock() }
        guard let previously = seen.updateValue(granted, forKey: c) else { return }
        guard granted, !previously else { return }
        arrivedAt = now
    }

    func secondsSinceGrantArrived(now: Double) -> Double? {
        lock.lock()
        defer { lock.unlock() }
        return arrivedAt.map { now - $0 }
    }
}

/// When each capability last produced something, in this process.
///
/// Stamped from capture paths on whatever thread they happen to be on — a screen tick on the main
/// actor, an audio pump off it — and read by the capability poll, so it takes the lock for the same
/// reason `RequestState` does.
private final class CaptureClock: @unchecked Sendable {
    private let lock = NSLock()
    private var stamps: [Capability: Double] = [:]

    func stamp(_ c: Capability) {
        let now = ContextTime.now
        lock.lock()
        stamps[c] = now
        lock.unlock()
    }

    func lastOutput(_ c: Capability) -> Double? {
        lock.lock()
        defer { lock.unlock() }
        return stamps[c]
    }
}

/// One-shot flag readable from another thread without blocking it.
private final class Latch: @unchecked Sendable {
    private let lock = NSLock()
    private var signalled = false

    func signal() {
        lock.lock()
        signalled = true
        lock.unlock()
    }

    /// Only `systemAudioTapRefused` clears, and only on a tap that succeeded. The other two hold
    /// facts a later success cannot undo inside one process: window-server capture rights are settled
    /// when the process connects, and a consent dialog macOS has spent stays spent.
    func clear() {
        lock.lock()
        signalled = false
        lock.unlock()
    }

    var isSignalled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return signalled
    }
}
