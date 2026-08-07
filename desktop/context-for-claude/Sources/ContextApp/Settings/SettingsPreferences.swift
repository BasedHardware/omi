import AppKit
import ContextCore
import SwiftUI

// MARK: - Appearance

/// What the Appearance tiles choose between.
///
/// `system` is the default and is not a third colour scheme — it is the absence of an override, which
/// is exactly what Phase 0 of `docs/first-run-experience.md` established when it deleted the forced
/// `NSApp.appearance = .aqua`. Light and Dark are opt-in overrides of that, so the mapping below has
/// to produce **nil** for `system` rather than a guess at what the system currently is: a stored
/// `.aqua` would go stale the moment the user's own Appearance setting changed.
enum AppearanceOverride: String, CaseIterable, Identifiable, Codable, Sendable {
    case system
    case light
    case dark

    var id: String { rawValue }

    var title: String {
        switch self {
        case .system: "System"
        case .light: "Light"
        case .dark: "Dark"
        }
    }

    /// The appearance to install on `NSApp`, or nil to follow the system.
    var nsAppearanceName: NSAppearance.Name? {
        switch self {
        case .system: nil
        case .light: .aqua
        case .dark: .darkAqua
        }
    }

    var nsAppearance: NSAppearance? {
        guard let nsAppearanceName else { return nil }
        return NSAppearance(named: nsAppearanceName)
    }
}

// There is deliberately no accent preference here.
//
// The Appearance pane used to offer one. It had exactly one consumer — `.tint()` on the Settings
// window — so it recoloured the switches on its own pane and nothing else: every structural accent
// in this app reads `Ink.accent`, which is a fixed `systemBlue` on purpose. Worse, its default case
// resolved to `NSColor.controlAccentColor`, so on a Mac whose system accent is Purple it painted the
// Settings window purple — the exact thing `Ink.accent` refuses to do for `INV-UI-1`
// (`docs/product/invariants/brand-ui.md`). A control that cannot do what it says and can only
// violate the brand rule is not a setting; it is removed rather than narrowed. `Ink.accent` remains
// the one accent, guarded by `InkAccentTests` and `BrandColourGuard`.

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

// MARK: - Timeline controls

/// Which of the timeline window's four controls are drawn.
///
/// Hiding a control never removes its keyboard shortcut — that is the promise the Appearance pane's
/// description makes, and it is why this is a *visibility* model rather than an enablement one.
struct TimelineControlVisibility: Equatable, Codable, Sendable {
    var openExternally: Bool = true
    var liveText: Bool = true
    var zoomControls: Bool = true
    var segmentNavigation: Bool = true

    /// One control, as the Appearance pane and the live preview both need it.
    enum Control: String, CaseIterable, Identifiable, Sendable {
        case openExternally
        case liveText
        case zoomControls
        case segmentNavigation

        var id: String { rawValue }

        var title: String {
            switch self {
            case .openExternally: "Open externally"
            case .liveText: "Live Text"
            case .zoomControls: "Zoom controls"
            case .segmentNavigation: "Segment navigation"
            }
        }

        var subtitle: String {
            switch self {
            case .openExternally:
                "Opens the webpage, file, or folder captured in this frame. The icon adapts to the content."
            case .liveText:
                "Highlights selectable and copyable text detected in the frame. "
                    + "Dims when no text has been detected yet."
            case .zoomControls:
                "Zooms the timeline track in and out. ⌘ + / − zooms the frame image instead."
            case .segmentNavigation:
                "Moves to the previous or next timeline segment. "
                    + "These chevrons sit on the left and right edges of the frame."
            }
        }

        /// The shortcut that keeps working when the control is hidden. Nil where the reference shows
        /// no hint — Live Text has no chord in `RewindView`, and inventing one here would be a hint
        /// that does nothing.
        var shortcutHint: String? {
            switch self {
            case .openExternally: "↵"
            case .liveText: nil
            case .zoomControls: "⌘ ⇧ + / −"
            case .segmentNavigation: "⌥ ← / →"
            }
        }

        /// The symbol the preview draws for this control, matching `RewindView`'s cluster.
        var previewSymbol: String {
            switch self {
            case .openExternally: "globe"
            case .liveText: "text.viewfinder"
            case .zoomControls: "plus.magnifyingglass"
            case .segmentNavigation: "chevron.right"
            }
        }
    }

    subscript(control: Control) -> Bool {
        get {
            switch control {
            case .openExternally: openExternally
            case .liveText: liveText
            case .zoomControls: zoomControls
            case .segmentNavigation: segmentNavigation
            }
        }
        set {
            switch control {
            case .openExternally: openExternally = newValue
            case .liveText: liveText = newValue
            case .zoomControls: zoomControls = newValue
            case .segmentNavigation: segmentNavigation = newValue
            }
        }
    }

    /// The controls the preview should draw, in `RewindView`'s order.
    var visible: [Control] { Control.allCases.filter { self[$0] } }
}

// MARK: - Capture

/// The four Capture Quality tiles.
///
/// Every subtitle states the resolution and the trade in words. It deliberately quotes **no**
/// per-frame byte figure: `ScreenWatcher`'s measured table (68.4 KB at HEIC q0.20, 110.2 KB at q0.40)
/// was taken at one downscale, so attaching those numbers to a different one would be a fabricated
/// measurement — the exact thing `J7` forbids.
enum CaptureQuality: String, CaseIterable, Identifiable, Codable, Sendable {
    case best
    case standard
    case compact
    case smallest

    var id: String { rawValue }

    /// `standard` is the tile that matches what capture ships today: `ScreenWatcher.maxPixelSize`
    /// 1600 and `frameQuality` 0.20.
    static let `default`: CaptureQuality = .standard

    var title: String {
        switch self {
        case .best: "Best Quality"
        case .standard: "Default"
        case .compact: "Compact"
        case .smallest: "Smallest"
        }
    }

    /// Longest side of the stored picture, in pixels.
    var longestSide: Int {
        switch self {
        case .best: 2400
        case .standard: 1600
        case .compact: 1280
        case .smallest: 1024
        }
    }

    /// HEIC lossy-compression quality. Note HEIC's scale is not JPEG's — see `ScreenWatcher`.
    var compressionQuality: Double {
        switch self {
        case .best: 0.40
        case .standard: 0.20
        case .compact: 0.15
        case .smallest: 0.10
        }
    }

    /// The line under the tile row, describing the *selected* tile.
    ///
    /// **`best` states its consequence, not only its cost.** "Largest files" is a disk-space remark
    /// and reads as one; what it leaves out is that on this app larger files also mean *less
    /// history*. `Engine.scheduleRetentionSweep` runs `enforceRetention(olderThanDays:toFitBytes:)`
    /// only when the strategy is `.limit`, and that sweep deletes oldest-first the moment the frames
    /// folder passes the user's threshold — so the same threshold that holds a month of Default
    /// frames holds materially less at 2400 px and q0.40. `ScreenWatcher.writeFrameImage` already
    /// documents this trade from the capture side ("A user who picks **Best Quality** is choosing to
    /// spend that headroom"); until now no string the user reads said it. Storage's own copy had to
    /// be fixed for exactly this omission — a bound that silently deletes data has to be disclosed
    /// where the choice is made, not where the machinery lives.
    ///
    /// No multiplier and no byte figure, for the reason this enum's own note gives: the measured
    /// table was taken at one downscale, and attaching it to another would be a fabricated
    /// measurement. The direction is what is provable, so the direction is what is claimed.
    var subtitle: String {
        switch self {
        case .best:
            "2400 px on the longest side · sharpest text, largest files. With Storage set to Limit, "
                + "the threshold is reached sooner, so the same threshold keeps fewer days of "
                + "history than it does at Default."
        case .standard: "1600 px on the longest side · sharp on Retina; recommended"
        case .compact: "1280 px on the longest side · readable, noticeably smaller"
        case .smallest: "1024 px on the longest side · layout and headings only"
        }
    }
}

// MARK: - Storage

/// The Storage pane's radio group.
///
/// `off` is the default, and it is the only option that cannot destroy anything.
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

    var title: String {
        switch self {
        case .off: "Off"
        case .limit: "Limit"
        }
    }

    /// **States the age bound as well as the threshold.** The sweep enforces both
    /// (`ContextStore.enforceRetention` prunes by age *and* by bytes), so copy that mentioned only
    /// the threshold meant a user who set 200 GB with 8 GB on disk still lost everything older than
    /// `StorageLimit.retentionDays` — permanent deletion of their data that no string disclosed.
    var subtitle: String {
        switch self {
        case .off: "Keep all your data. Forever."
        case .limit:
            "Limit Storage. Deletes the oldest recordings when the threshold is reached, and "
                + "everything older than \(StorageLimit.retentionDays) days whatever the threshold is."
        }
    }

    var symbol: String {
        switch self {
        case .off: "pause.circle"
        case .limit: "trash"
        }
    }

    /// True for anything that irreversibly changes what is already on disk.
    ///
    /// `limit` deletes recordings outright, and it may not be reachable by one stray click on a
    /// radio button.
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

    /// Deliberately not `ContextStore.defaultFrameBytesCap` (4 GiB): that cap is the app's own
    /// backstop and applies whether or not the user asked for a limit. This is the number they chose.
    static let defaultBytes: Int64 = 5 * gigabyte
    static let minimumBytes: Int64 = gigabyte
    static let maximumBytes: Int64 = 200 * gigabyte
    static let stepBytes: Int64 = gigabyte

    /// The age bound the retention sweep is started with, in days.
    ///
    /// `Limit` is two bounds, not one: `ContextStore.enforceRetention` calls `pruneFrames(olderThanDays:)`
    /// *and* `pruneFrames(toFitBytes:)`, and `Engine.ensureStorage` passes `olderThanDays: 30`. So
    /// turning Limit on deletes everything older than a month even when the disk figure is nowhere
    /// near the threshold — and until this constant existed, not one string the user reads said so.
    ///
    /// Pinned as a literal because the number is passed inline at that call site, in a file this one
    /// does not own. It lives here so the three strings that must disclose the age prune — the radio
    /// row, the threshold row and the confirmation — cannot drift apart from each other.
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

    private enum Key {
        static let appearance = "context.settings.appearance"
        /// Not a second copy of the string: the launch path reads the same key through
        /// `DockPresence`, and a rename that only reached one of them would be silent.
        static let showsDockIcon = DockPresence.defaultsKey
        static let timelineControls = "context.settings.timelineControls"
        static let screenCapture = "context.settings.screenCapture"
        static let pausesOnInactivity = "context.settings.pausesOnInactivity"
        static let captureQuality = "context.settings.captureQuality"
        static let storageStrategy = "context.settings.storageStrategy"
        static let storageLimitBytes = "context.settings.storageLimitBytes"
        static let claudeTarget = "context.settings.claudeTarget"
    }

    private let defaults: UserDefaults
    /// False in tests: `NSApp` is not a real application there, and installing an appearance or an
    /// activation policy on it is neither meaningful nor safe.
    private let appliesToRunningApp: Bool

    // MARK: Appearance

    @Published var appearance: AppearanceOverride {
        didSet {
            guard appearance != oldValue else { return }
            defaults.set(appearance.rawValue, forKey: Key.appearance)
            applyAppearance()
        }
    }

    @Published var showsDockIcon: Bool {
        didSet {
            guard showsDockIcon != oldValue else { return }
            defaults.set(showsDockIcon, forKey: Key.showsDockIcon)
            applyDockIcon()
        }
    }

    @Published var timelineControls: TimelineControlVisibility {
        didSet {
            guard timelineControls != oldValue else { return }
            guard let data = try? JSONEncoder().encode(timelineControls) else { return }
            defaults.set(data, forKey: Key.timelineControls)
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

    @Published var captureQuality: CaptureQuality {
        didSet {
            guard captureQuality != oldValue else { return }
            defaults.set(captureQuality.rawValue, forKey: Key.captureQuality)
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
            guard let raw = defaults.string(forKey: key), let value = T(rawValue: raw) else { return fallback }
            return value
        }
        func flag(_ key: String, default fallback: Bool) -> Bool {
            defaults.object(forKey: key) as? Bool ?? fallback
        }

        self.appearance = enumValue(Key.appearance, AppearanceOverride.system)
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
        if let data = defaults.data(forKey: Key.timelineControls),
            let decoded = try? JSONDecoder().decode(TimelineControlVisibility.self, from: data)
        {
            self.timelineControls = decoded
        } else {
            self.timelineControls = TimelineControlVisibility()
        }
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
        self.captureQuality = enumValue(Key.captureQuality, CaptureQuality.default)
        self.storage = StorageSelection(strategy: enumValue(Key.storageStrategy, StorageStrategy.off))
        let storedLimit = defaults.object(forKey: Key.storageLimitBytes) as? Int
        self.storageLimitBytes = StorageLimit.clamp(Int64(storedLimit ?? Int(StorageLimit.defaultBytes)))
        self.claudeTarget = enumValue(Key.claudeTarget, ClaudeRouter.Target.claudeApp)

        applyAppearance()
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
            "limited to \(StorageLimit.format(storageLimitBytes)) and to the last "
                + "\(StorageLimit.retentionDays) days"
        }
    }

    // MARK: Application

    private func applyAppearance() {
        guard appliesToRunningApp, NSApp != nil else { return }
        NSApp.appearance = appearance.nsAppearance
    }

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
