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
            // A CoreAudio process tap is consented to as audio capture, so its switch sits in the
            // Microphone pane. There is no separate system-audio pane to send anyone to.
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
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
    @discardableResult
    static func request(_ c: Capability) async -> Bool {
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
            openSettings(for: c)
            return AXElement.isTrusted
        }
    }

    static func openSettings(for c: Capability) {
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

    static func relaunchApp() -> Never {
        let url = Bundle.main.bundleURL
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.createsNewApplicationInstance = true
        configuration.activates = true

        let launch = Latch()
        NSWorkspace.shared.openApplication(at: url, configuration: configuration) { app, error in
            if let error {
                ContextLog.error("Relaunch failed: \(error.localizedDescription)", "permissions")
            } else {
                ContextLog.info("Relaunched \(url.lastPathComponent) as pid \(app?.processIdentifier ?? -1)", "permissions")
            }
            launch.signal()
        }

        // The replacement has to be up before this process dies, or the user is left with no app at
        // all and no way back except Finder. Pump the runloop rather than block it: this is called
        // from a button, and a bare semaphore wait on the main thread stalls the very runloop
        // LaunchServices replies on.
        let deadline = Date().addingTimeInterval(10)
        while !launch.isSignalled && Date() < deadline {
            if Thread.isMainThread {
                RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
            } else {
                usleep(50_000)
            }
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
            openSettings(for: .microphone)
            return false
        }
    }

    private static func requestScreen() async -> Bool {
        if CGPreflightScreenCaptureAccess() { return true }

        guard !hasPrompted(.screen) else {
            // `CGRequestScreenCaptureAccess` returns false immediately once the answer is on record;
            // calling it again would make the row feel dead.
            openSettings(for: .screen)
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
            openSettings(for: .systemAudio)
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

    private static let systemAudioProbeInterval: Double = 30

    /// The last answer we got from an actual tap. Never probes: probing from a background poll would
    /// raise the consent dialog behind the user's back, and that prompt belongs to the row they tap.
    private static func cachedSystemAudioGrant() -> Bool {
        guard let cached = defaults.object(forKey: Key.systemAudioGranted) as? Bool else {
            return false  // never probed — unknown, reported as "Open" rather than guessed at
        }
        if !cached, ContextTime.now - defaults.double(forKey: Key.systemAudioProbedAt) > systemAudioProbeInterval {
            // A denial can be reversed in System Settings without telling us, and re-probing is
            // silent once the answer is on record. A grant, by contrast, is trusted for the life of
            // the process: a second global tap while capture is live is the one thing that can knock
            // the live tap over.
            scheduleSystemAudioProbe()
        }
        return cached
    }

    private static func scheduleSystemAudioProbe() {
        guard state.beginIfIdle(.systemAudio) else { return }
        // Stamp before the work so a burst of polls cannot queue a second probe behind this one.
        defaults.set(ContextTime.now, forKey: Key.systemAudioProbedAt)
        DispatchQueue.global(qos: .utility).async {
            let granted = primeSystemAudioTap()
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
}

/// `PermissionAsking` on the real `Permissions`.
@MainActor
struct LivePermissionAsking: PermissionAsking {
    func isGranted(_ capability: Capability) -> Bool { Permissions.check(capability) }
    func request(_ capability: Capability) async -> Bool { await Permissions.request(capability) }
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
/// - `settle` polls until the grant reads back, because TCC answers the dialog before it finishes
///   writing the grant, and a check taken the instant `request` returns still reads false — the row
///   would flash "action required" over a permission the user just gave.
///
/// It is bounded and indifferent to the answer. A decline never becomes true, so `settle` returns on
/// its deadline and the run carries on to the next capability rather than stalling on a "no".
@MainActor
struct PermissionRun {
    /// How long a row is lit before its dialog opens.
    static let leadIn: Duration = .milliseconds(900)
    /// How long the new checkmark sits alone before the next dialog opens over it.
    static let afterGrant: Duration = .milliseconds(1_100)
    /// The longest we wait for TCC to finish writing a grant it has already accepted.
    static let settleDeadline: Duration = .seconds(2)
    static let settlePoll: Duration = .milliseconds(120)

    let asking: any PermissionAsking
    var leadIn: Duration = PermissionRun.leadIn
    var afterGrant: Duration = PermissionRun.afterGrant
    var settleDeadline: Duration = PermissionRun.settleDeadline
    var settlePoll: Duration = PermissionRun.settlePoll

    /// What the view needs to know as the run moves.
    struct Callbacks {
        /// The row is lit and nothing is covering it yet.
        var willAsk: (Capability) -> Void = { _ in }
        /// The answer is in and has been read back. `granted` is what TCC actually reports now, not
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

            _ = await asking.request(capability)
            let granted = await settle(capability)
            if granted { landed.insert(capability) }
            callbacks.didAnswer(capability, granted)

            try? await Task.sleep(for: afterGrant)
        }
        return landed
    }

    /// Polls until the grant reads back or the deadline passes. Never waits on a refusal.
    private func settle(_ capability: Capability) async -> Bool {
        if asking.isGranted(capability) { return true }
        let deadline = ContinuousClock.now.advanced(by: settleDeadline)
        while ContinuousClock.now < deadline {
            try? await Task.sleep(for: settlePoll)
            if asking.isGranted(capability) { return true }
        }
        return false
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
