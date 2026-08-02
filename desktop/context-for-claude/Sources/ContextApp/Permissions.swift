import AVFoundation
import ContextCore
import AppKit
import CoreGraphics
import Foundation

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

    static func check(_ c: Capability) -> Bool {
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
            return CGPreflightScreenCaptureAccess()
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
    static func promptIsSpent(_ c: Capability) -> Bool { hasPrompted(c) }

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

    // MARK: - Screen Recording relaunch

    /// Screen Recording only takes effect after a relaunch — the UI has to say so rather than
    /// leaving the user staring at a granted checkbox and a dead capture.
    ///
    /// The window server decides what a process may capture when that process connects, so a grant
    /// made while Context for Claude is running applies to the *next* Context for Claude, never this one.
    static var screenNeedsRelaunch: Bool {
        guard CGPreflightScreenCaptureAccess() else {
            // Nothing granted, so nothing is waiting on a relaunch.
            defaults.set(false, forKey: Key.screenPendingRelaunch)
            return false
        }
        if !screenGrantedAtLaunch {
            // First time we see the grant inside a process that started without it. Persisted so the
            // nudge survives a crash before the user gets around to reopening.
            defaults.set(true, forKey: Key.screenPendingRelaunch)
        }
        return defaults.bool(forKey: Key.screenPendingRelaunch)
    }

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
    static func relaunchApp() -> Never {
        guard spawnRelaunchHelper() else {
            // Nothing left to try, and exiting anyway would be the worst outcome: the user pressed a
            // button labelled "Restart to finish" and would be left with no app and no Dock icon to
            // reopen it from. Stay up instead — the card is still on screen and the menu bar still
            // offers Quit — rather than terminate into nothing.
            ContextTelemetry.recordFallback(
                area: .settings, from: "relaunch", to: "stay-running",
                reason: "helper-spawn-failed", outcome: .degraded)
            while true { RunLoop.current.run(mode: .default, before: .distantFuture) }
        }
        exit(0)
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

    private static func requestScreen() async -> Bool {
        if CGPreflightScreenCaptureAccess() { return true }

        guard !hasPrompted(.screen) else {
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
        let cached = defaults.object(forKey: Key.systemAudioGranted) as? Bool
        if systemAudioProbeIsDue(
            cached: cached,
            prompted: hasPrompted(.systemAudio),
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
        recordSystemAudio(granted)
        return granted
    }

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
        if previous != granted {
            ContextLog.info("System audio consent is now \(granted ? "granted" : "denied")", "permissions")
        }
    }

    // MARK: - Status words

    /// The four words the permission row can show, per `docs/design-system.md`.
    private enum Word {
        static let granted = "Granted"
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
        static let screenPendingRelaunch = "context.permission.screen.pendingRelaunch"

        static func prompted(_ c: Capability) -> String {
            "context.permission.\(c.rawValue).prompted"
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
            return """
                System Settings is open on the right row. Switch it on and I’ll notice — I won’t \
                move on without an answer. If now is not the time, tell me and I’ll ask again \
                later. \(waitingDetail(for: capability))
                """
        case .confirming(let capability):
            if capability == .screen, asking.screenNeedsRelaunch {
                return "Granted. I’ll need to be reopened before I can actually see the screen."
            }
            return "Got it."
        case .blocked:
            return "Still waiting on an answer."
        }
    }

    private func waitingDetail(for capability: Capability) -> String {
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

/// One-shot flag readable from another thread without blocking it.
private final class Latch: @unchecked Sendable {
    private let lock = NSLock()
    private var signalled = false

    func signal() {
        lock.lock()
        signalled = true
        lock.unlock()
    }

    var isSignalled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return signalled
    }
}
