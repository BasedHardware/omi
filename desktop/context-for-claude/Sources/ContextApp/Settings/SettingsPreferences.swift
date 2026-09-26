import AppKit
import ContextCore
import SwiftUI

// MARK: - Appearance

// **There is no appearance preference in this app, and there is no Appearance pane.**
//
// Three controls used to live there and all three are gone rather than narrowed:
//
// - **The theme tiles** (System / Light / Dark) wrote `NSApp.appearance`. `System` — the default and
//   what every install was on — installed nothing at all, so the whole control existed to let a user
//   *disagree* with their own machine's Appearance setting inside one app. Phase 0 of
//   `docs/first-run-experience.md` had already deleted a forced `NSApp.appearance = .aqua` for
//   rendering a light popover inside a dark system menu; the tiles were the same defect with a
//   switch on it. The app follows the system, full stop.
// - **The accent picker**, removed earlier, reached `.tint()` on the Settings window and nothing
//   else — every structural accent reads `Ink.accent` — while its default resolved to
//   `NSColor.controlAccentColor`, painting the window purple on a Mac set to Purple, which is
//   exactly what `INV-UI-1` (`product/invariants/brand-ui.md`) forbids.
// - **The timeline control toggles**, four switches that hid the timeline's own buttons. See
//   `Rewind/RewindView.swift`.
//
// The one row on that pane that did something a user wants, **Show Dock Icon**, moved to General;
// `DockPresence` below is unchanged and still owns its key, its default and its mapping.

// MARK: - The Dock

/// **Whether this process shows a Dock icon, and which of AppKit's two app shapes that makes it.**
///
/// Free-standing rather than a computed property on `SettingsStore`, because the decision has two
/// callers and the second one must not build the store. `ContextAppDelegate` applies it in
/// `applicationDidFinishLaunching` — before anything can draw, and long before the user has opened
/// Settings — while the store applies it again each time the row is switched. Two readers of one
/// `UserDefaults` key drift the moment either writes its own default inline, so the key, the default
/// and the mapping all live here and both callers go through them. `DockPresenceTests` is the
/// assertion that they still do.
///
/// **The default is on, and `Resources/Info.plist` is written to match it.** `LSUIElement` is
/// `false` there, so the process starts `.regular`, macOS builds the app's main menu during launch,
/// and this type only ever has work to do for the user who turned the row off. The alternative —
/// stay `LSUIElement` and promote to `.regular` from Swift — is the transition that leaves a
/// promoted app holding a Dock icon and no menu bar until it has been deactivated and reactivated.
/// Demotion is the direction that behaves, so the minority case is the one that transitions.
enum DockPresence {

    /// Namespaced with the app's other `context.settings.*` defaults, and the single owner of the
    /// string: `SettingsStore.Key.showsDockIcon` is this constant rather than a second copy of it.
    static let defaultsKey = "context.settings.showsDockIcon"

    /// **On**, and this reverses the divergence the row shipped with.
    ///
    /// It used to be off, on the reasoning that a Dock icon is "the single most visible way this
    /// product could stop being ambient" — which is half of a real trade and was shipped as if it
    /// were all of it. The other half is the report: on a menu bar carrying thirty extras, this
    /// app's mark is genuinely hard to find, and an app nobody can find is not ambient either, it
    /// is missing. The reference this pane is built from (`docs/rewind-and-settings.md`, Appearance)
    /// always specified "toggle, on"; the row still works in both directions for anyone who wants
    /// the menu-bar-only shape back.
    static let showsByDefault = true

    /// The whole of the mapping, as a function of the preference, so it is assertable without an
    /// `NSApplication` to install it on.
    ///
    /// `.prohibited` is deliberately not a third case. It is not "even more hidden than
    /// `.accessory`" — it is an app that may not come to the foreground at all, which would take the
    /// status item's popover and every window this app owns with it.
    static func activationPolicy(showsDockIcon: Bool) -> NSApplication.ActivationPolicy {
        showsDockIcon ? .regular : .accessory
    }

    /// `object(forKey:)` and not `bool(forKey:)`. The latter answers `false` for a key nobody has
    /// written, so it cannot tell "turned off" from "never opened Settings" — and every install in
    /// the field is the second one. A reader that used it would hand exactly those users the
    /// opposite of `showsByDefault`.
    static func showsDockIcon(in defaults: UserDefaults) -> Bool {
        defaults.object(forKey: defaultsKey) as? Bool ?? showsByDefault
    }

    /// What `applicationDidFinishLaunching` installs on `NSApp`.
    static func launchPolicy(reading defaults: UserDefaults = .standard) -> NSApplication.ActivationPolicy {
        activationPolicy(showsDockIcon: showsDockIcon(in: defaults))
    }
}

// MARK: - Storage

/// The Storage pane's radio group.
///
/// **`limit` is the default, and what it deletes is pictures — never text.** It used to be `off`,
/// on the reasoning that `off` "is the only option that cannot destroy anything", and that was the
/// right call while `limit` deleted whole frame rows: turning it on threw away the OCR, the
/// accessibility text and every FTS entry for a moment along with its screenshot, so the safe
/// default was to enforce nothing at all. `ContextStore.expireFrameImages` changed what the option
/// means. A frame past the horizon now keeps its row and all of its text and loses only the image,
/// which is 88% of what a year of capture costs (27.0 KB per stored image against 3.7 KB of
/// database per frame, measured) and the one part no reader opens: `recall`, `screen` and the
/// search panel all read `ocrText`/`axText`.
///
/// So the two options no longer trade *history* against disk — they trade **pictures** against
/// disk, and `off` is no longer the cautious choice so much as the unbounded one. It kept its
/// promise by having no backstop whatsoever: a Mac left at login accumulated screenshots forever,
/// measured at ~1.8 GB a year on a machine that captures lightly.
///
/// `off` remains, unchanged and one click away, for anyone who wants the pictures kept too.
///
/// **There is no `compress` case.** The pane used to offer one behind a red destructive confirmation
/// reading "The original detail cannot be recovered", and nothing anywhere re-encoded a frame:
/// `EngineStore.scheduleRetentionSweep` tests `strategy == .limit` and no re-encoder exists in this
/// package. A destructive-role warning in front of a no-op is worse than a missing feature — it
/// teaches the user that this app's warnings mean nothing, and the next one is the one that really
/// deletes. A stored `"compress"` from an older build decodes to nil and therefore falls back to
/// `off` in both readers (`SettingsStore.init` and the sweep), which is the safe direction and is
/// why no migration is needed.
enum StorageStrategy: String, CaseIterable, Identifiable, Codable, Sendable {
    case off
    case limit

    var id: String { rawValue }

    /// The shipped default. Named rather than written inline because two readers have to agree on
    /// it: this store, and `Engine.scheduleRetentionSweep`, which parses the same defaults key on
    /// its own. `SettingsStore.init` registers it so both answer the same way for an install that
    /// has never opened this pane.
    static let `default`: StorageStrategy = .limit

    var title: String {
        switch self {
        case .off: "Keep screenshots"
        case .limit: "Expire screenshots"
        }
    }

    /// **States the age bound as well as the threshold, and states what survives.** The sweep
    /// enforces both bounds (`ContextStore.enforceRetention` expires by age *and* by bytes), so copy
    /// that mentioned only the threshold meant a user who set 200 GB with 8 GB on disk still lost
    /// every screenshot older than `StorageLimit.retentionDays` with nothing disclosing it.
    ///
    /// The second half — "the text is kept" — is load-bearing now that this is the default. A user
    /// who never opens this pane has still agreed to nothing, so the row that is selected for them
    /// has to say exactly what it does the first time they read it.
    var subtitle: String {
        switch self {
        case .off: "Keep everything, screenshots included, for as long as there is disk for it."
        case .limit:
            "Keeps the text of every screen moment forever, and deletes the screenshot itself "
                + "after \(StorageLimit.retentionDays) days — or sooner, once the screenshots on "
                + "disk pass the threshold. Searching your history still finds these moments; they "
                + "just no longer have a picture."
        }
    }

    var symbol: String {
        switch self {
        case .off: "infinity"
        case .limit: "photo.badge.arrow.down"
        }
    }

    /// True for anything that irreversibly changes what is already on disk.
    ///
    /// `limit` unlinks screenshots that are already there, and *switching to it* may not be
    /// reachable by one stray click on a radio button.
    ///
    /// It being the default does not weaken this. A default is not a click, so it does not raise
    /// the sheet — which is exactly why `subtitle` above and the pane's own footnote have to state
    /// the behaviour outright rather than leaving the disclosure to a dialog most users will never
    /// see. The sheet still guards the deliberate act of turning it back on after turning it off.
    var destroysExistingData: Bool {
        switch self {
        case .off: false
        case .limit: true
        }
    }
}

/// The radio group's state machine: what is committed, and what is waiting for a yes.
///
/// Split out from the view so "Limit needs a confirmation" is a property of a value that can be
/// tested, rather than of a sheet that cannot.
struct StorageSelection: Equatable, Sendable {
    /// What is actually in force.
    private(set) var strategy: StorageStrategy
    /// Chosen but not yet confirmed. The radio group shows this as selected so the user can see what
    /// they are being asked about, but nothing else in the app reads it.
    private(set) var pending: StorageStrategy?

    init(strategy: StorageStrategy = .off) {
        self.strategy = strategy
    }

    enum Outcome: Equatable, Sendable {
        case committed
        case awaitingConfirmation
        case unchanged
    }

    /// What the radio group draws as selected.
    var highlighted: StorageStrategy { pending ?? strategy }

    var isAwaitingConfirmation: Bool { pending != nil }

    @discardableResult
    mutating func select(_ next: StorageStrategy) -> Outcome {
        guard next != strategy || pending != nil else { return .unchanged }
        guard next.destroysExistingData else {
            pending = nil
            strategy = next
            return .committed
        }
        pending = next
        return .awaitingConfirmation
    }

    /// The second deliberate action. Only ever promotes what `select` parked.
    @discardableResult
    mutating func confirm() -> Outcome {
        guard let pending else { return .unchanged }
        strategy = pending
        self.pending = nil
        return .committed
    }

    mutating func cancel() {
        pending = nil
    }
}

/// The threshold the Limit strategy deletes down to.
enum StorageLimit {
    /// A gigabyte as `ByteCountFormatter(.file)` counts one, i.e. decimal.
    ///
    /// Not 1024³, and that is the whole point: the threshold is *displayed* through that formatter, so a
    /// 5 × 1024³ default rendered as "5.37 GB" — in the confirmation title, in the stepper and in the
    /// header — while the stepper moved in whole binary gigabytes. Every number the user sees here is a
    /// round one because the unit they are stored in is the unit they are printed in.
    static let gigabyte: Int64 = 1_000_000_000

    /// Deliberately not `ContextStore.defaultFrameBytesCap` (4 GiB). That constant is only the
    /// *default argument* of `ContextStore.enforceRetention(olderThanDays:toFitBytes:)`, and nothing
    /// in this app takes it: `Engine.scheduleRetentionSweep` runs only when the strategy is `.limit`
    /// and always passes this number explicitly. So there is still no 4 GiB backstop under a user
    /// who has chosen **Keep screenshots** — that user keeps every picture, forever, exactly as the
    /// radio row promises.
    ///
    /// Said here because this comment used to claim the opposite ("that cap is the app's own backstop
    /// and applies whether or not the user asked for a limit"), and a note that describes a bound
    /// nothing enforces is how the next person to read it writes copy promising one.
    static let defaultBytes: Int64 = 5 * gigabyte
    static let minimumBytes: Int64 = gigabyte
    static let maximumBytes: Int64 = 200 * gigabyte
    static let stepBytes: Int64 = gigabyte

    /// The age bound the retention sweep is started with, in days.
    ///
    /// `Expire screenshots` is two bounds, not one: `ContextStore.enforceRetention` calls
    /// `expireFrameImages(olderThanDays:)` *and* `expireFrameImages(toFitBytes:)`, and
    /// `Engine.ensureStorage` passes `olderThanDays: 30`. So the screenshot for a moment a month old
    /// is deleted even when the disk figure is nowhere near the threshold — and until this constant
    /// existed, not one string the user reads said so.
    ///
    /// Pinned as a literal because the number is passed inline at that call site, in a file this one
    /// does not own. It lives here so the four strings that must disclose the age bound — the radio
    /// row, the threshold row, the pane's footnote and the confirmation — cannot drift apart from
    /// each other.
    static let retentionDays = 30

    static func clamp(_ bytes: Int64) -> Int64 {
        min(max(bytes, minimumBytes), maximumBytes)
    }

    /// `709.7 MB`, `5.0 GB` — the same shape the reference header uses.
    static func format(_ bytes: Int64) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        formatter.allowedUnits = [.useKB, .useMB, .useGB, .useTB]
        return formatter.string(fromByteCount: max(0, bytes))
    }
}

// MARK: - Agents

// There is deliberately no `AgentRoute` here either.
//
// The Agents pane used to offer a "Route to Agent" picker whose subtitle promised that ⌘↵ sent the
// query to the chosen agent. Nothing read the preference, and no ⌘↵ chord exists: `SearchBarView`
// handles `insertNewline:` only, and routing what is typed into the bar off to Claude is the path
// divergence 3 in `docs/requirements-checklist.md` deliberately removed. The one agent routing
// decision that is real is `claudeTarget`, below, which `ClaudeHandoff` reads.

// MARK: - The store

/// Every Settings preference this app owns, in one observable place.
///
/// Three settings on these panes are deliberately **not** here, because something else is already
/// their source of truth and a second copy is how "the user turned it off and it kept doing it"
/// happens:
///
/// - **Launch on Login** is `SMAppService.mainApp.status`, read live through `LoginItem` — the user
///   can remove a login item in System Settings at any time.
/// - **Airgap Mode** is `ExclusionEngine`, which is also what enforces it for favicons.
/// - **Music** is `SoundController.musicEnabledDefaultsKey`, owned by `Sound`.
@MainActor
final class SettingsStore: ObservableObject {

    static let shared = SettingsStore()

    /// **Three retired keys are deliberately not listed and deliberately not migrated:**
    /// `context.settings.appearance`, `context.settings.timelineControls` and
    /// `context.settings.captureQuality`. Nothing reads them any more, so a stored value from an
    /// older build is inert — which is the whole of the migration. Deleting them at launch would
    /// be a write over a user's disk to tidy up after ourselves, and it would make a downgrade lose
    /// the setting for real.
    private enum Key {
        /// Not a second copy of the string: the launch path reads the same key through
        /// `DockPresence`, and a rename that only reached one of them would be silent.
        static let showsDockIcon = DockPresence.defaultsKey
        static let screenCapture = "context.settings.screenCapture"
        static let pausesOnInactivity = "context.settings.pausesOnInactivity"
        static let storageStrategy = "context.settings.storageStrategy"
        static let storageLimitBytes = "context.settings.storageLimitBytes"
        static let claudeTarget = "context.settings.claudeTarget"
    }

    private let defaults: UserDefaults
    /// False in tests: `NSApp` is not a real application there, and installing an activation policy
    /// on it is neither meaningful nor safe.
    private let appliesToRunningApp: Bool

    // MARK: The Dock

    @Published var showsDockIcon: Bool {
        didSet {
            guard showsDockIcon != oldValue else { return }
            defaults.set(showsDockIcon, forKey: Key.showsDockIcon)
            applyDockIcon()
        }
    }

    // MARK: Capture

    @Published var screenCaptureEnabled: Bool {
        didSet {
            guard screenCaptureEnabled != oldValue else { return }
            defaults.set(screenCaptureEnabled, forKey: Key.screenCapture)
        }
    }

    @Published var pausesOnInactivity: Bool {
        didSet {
            guard pausesOnInactivity != oldValue else { return }
            defaults.set(pausesOnInactivity, forKey: Key.pausesOnInactivity)
        }
    }

    // MARK: Storage

    /// Only ever written through `selectStorage`/`confirmStorage`, which is what keeps the
    /// confirmation from being bypassable by a binding.
    @Published private(set) var storage: StorageSelection

    @Published var storageLimitBytes: Int64 {
        didSet {
            let clamped = StorageLimit.clamp(storageLimitBytes)
            if clamped != storageLimitBytes {
                storageLimitBytes = clamped
                return
            }
            guard storageLimitBytes != oldValue else { return }
            defaults.set(Int(storageLimitBytes), forKey: Key.storageLimitBytes)
        }
    }

    // MARK: Agents

    @Published var claudeTarget: ClaudeRouter.Target {
        didSet {
            guard claudeTarget != oldValue else { return }
            defaults.set(claudeTarget.rawValue, forKey: Key.claudeTarget)
        }
    }

    // MARK: Init

    init(defaults: UserDefaults = .standard, appliesToRunningApp: Bool = true) {
        self.defaults = defaults
        self.appliesToRunningApp = appliesToRunningApp

        func enumValue<T: RawRepresentable>(_ key: String, _ fallback: T) -> T where T.RawValue == String {
            guard let raw = defaults.string(forKey: key), let value = T(rawValue: raw) else {
                return fallback
            }
            return value
        }
        func flag(_ key: String, default fallback: Bool) -> Bool {
            defaults.object(forKey: key) as? Bool ?? fallback
        }

        // **On**, and the default is `DockPresence`'s rather than a literal here.
        //
        // It was off, as a deliberate divergence from the reference's "toggle, on", because this app
        // was `LSUIElement` and appearing in the Dock was called "the single most visible way this
        // product could stop being ambient". The divergence is reversed and the reason is in
        // `DockPresence.showsByDefault`: a mark lost among thirty menu-bar extras is not ambient
        // either. What matters here is only that the literal is gone — this store and the launch
        // path have to answer the same question the same way for an install that has never opened
        // Settings, and two `false`s written in two files is how that stops being true.
        self.showsDockIcon = flag(Key.showsDockIcon, default: DockPresence.showsByDefault)
        self.screenCaptureEnabled = flag(Key.screenCapture, default: true)
        // **Off** by default, a second deliberate divergence from the reference's "toggle, on", and
        // for a sharper reason than the Dock row's.
        //
        // This preference was inert until `ScreenWatcher.tick` started reading it — that line is its
        // first reader in the history of the package. So no existing install has a stored value:
        // every one of them falls through to this default. Shipping `true` would mean every user who
        // has never opened this pane silently stops being captured five minutes after they stop
        // typing (`CaptureActivity.idleThreshold`, 300s), on the strength of a switch they never
        // touched and whose effect they have never seen. A default is consent by omission, and there
        // is no omission to read here: the control has never done anything, so nobody has agreed to
        // what it now does.
        //
        // It is worse than a behaviour change, because the behaviour change is invisible. The idle
        // branch calls `noteSkip("machine idle")`, which writes one log line; it does not reach
        // `Engine.pausedReason`, which is what `MenuBar/StatusView` draws. So the menu bar reads
        // *Listening* while nothing is captured — the one signal that would let a user notice and
        // find this switch. Defaulting on while that is true ships a silent capture gap.
        //
        // `false` is also the recoverable direction. A user who wants the pause turns it on and has
        // then chosen the invisible-pause behaviour knowingly; a user who never wanted it keeps
        // exactly the capture they have today. Reversing this — making it on by default — is safe
        // once the paused state is visible in the menu bar, which is `Capture/`/`Engine.swift` work
        // and not this pane's to do.
        self.pausesOnInactivity = flag(Key.pausesOnInactivity, default: false)
        // **Registered, not written.** `Engine.scheduleRetentionSweep` reads this key straight out
        // of `UserDefaults` rather than through this store, and its own inline fallback is `.off` —
        // so a default declared only here would be a default the sweep never saw, and the strategy
        // this pane draws as selected would not be the one running. Registering puts the value in
        // the volatile registration domain, where `string(forKey:)` finds it, which makes the two
        // readers agree without this store having to fabricate a stored preference.
        //
        // `defaults.set` is deliberately not used: a written value is indistinguishable from a
        // choice the user made, forever, and would survive a later change of default. This is the
        // same reasoning `DockPresence.showsDockIcon` records for reading with `object(forKey:)`.
        //
        // The fallback below stays `.off`, and the two are not the same thing. Registration answers
        // "nothing is stored", which is every install that has never opened this pane; the fallback
        // answers "something unreadable is stored", which is the retired `"compress"` value. Engine's
        // own parse falls back to `.off` for that case, so this one must too — a default reached by
        // *both* readers is the point, and a pane claiming to expire screenshots while the sweep
        // does nothing would be worse than either behaviour on its own.
        defaults.register(defaults: [Key.storageStrategy: StorageStrategy.default.rawValue])
        self.storage = StorageSelection(strategy: enumValue(Key.storageStrategy, StorageStrategy.off))
        let storedLimit = defaults.object(forKey: Key.storageLimitBytes) as? Int
        self.storageLimitBytes = StorageLimit.clamp(Int64(storedLimit ?? Int(StorageLimit.defaultBytes)))
        self.claudeTarget = enumValue(Key.claudeTarget, ClaudeRouter.Target.claudeApp)

        applyDockIcon()
    }

    // MARK: Storage, behind its confirmation

    @discardableResult
    func selectStorage(_ strategy: StorageStrategy) -> StorageSelection.Outcome {
        var next = storage
        let outcome = next.select(strategy)
        storage = next
        if outcome == .committed { persistStorageStrategy() }
        return outcome
    }

    @discardableResult
    func confirmStorage() -> StorageSelection.Outcome {
        var next = storage
        let outcome = next.confirm()
        storage = next
        if outcome == .committed { persistStorageStrategy() }
        return outcome
    }

    func cancelStorageChange() {
        var next = storage
        next.cancel()
        storage = next
    }

    private func persistStorageStrategy() {
        defaults.set(storage.strategy.rawValue, forKey: Key.storageStrategy)
    }

    // MARK: Derived

    /// What the Storage header says beside the measured usage.
    ///
    /// Names both bounds for the same reason the radio row does: the sweep prunes by age as well as
    /// by size, and this caption is the one line a user reads without opening anything.
    var storageLimitSummary: String {
        switch storage.strategy {
        case .off: "no storage limits set"
        case .limit:
            "text kept forever · screenshots kept for \(StorageLimit.retentionDays) days "
                + "or \(StorageLimit.format(storageLimitBytes)), whichever comes first"
        }
    }

    // MARK: Application

    /// Live, in both directions, which is what lets the row's subtitle promise what it promises with
    /// no "takes effect on relaunch" caveat under it: `setActivationPolicy` adds and removes the Dock
    /// icon for the running process, and the status item is untouched by it either way — an
    /// `NSStatusItem` belongs to the status bar, not to the activation policy, so the app never loses
    /// both of its homes at once.
    ///
    /// The mapping is `DockPresence`'s and not restated here. `ContextAppDelegate` installs the same
    /// mapping over the same key at launch, and a switch that meant one thing on click and another
    /// after a relaunch is the defect that pairing is written to make impossible.
    private func applyDockIcon() {
        guard appliesToRunningApp, NSApp != nil else { return }
        NSApp.setActivationPolicy(DockPresence.activationPolicy(showsDockIcon: showsDockIcon))
    }
}

// MARK: - Version

/// The real version, from the bundle that is running.
///
/// The one version string in the app: `ContextUpdater.currentVersionDescription` reads this rather
/// than reaching for the plist a second time, so the Updates row and everything else can never
/// disagree about what is running. `docs/releasing.md` covers how a newer one reaches a user.
enum AppVersion {
    static var short: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
    }

    static var build: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown"
    }

    /// `Version 1.0.0 (1)`, matching the reference's shape.
    static var display: String { "Version \(short) (\(build))" }
}
