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

/// The accent choices offered in the Appearance pane.
///
/// **Purple is not in this list and cannot be added** — `INV-UI-1`
/// (`docs/product/invariants/brand-ui.md`) makes it off-brand anywhere in the product. Pink and
/// magenta are absent for the same reason `RewindPalette` stops its hue arc at 250°: at accent
/// saturation they read as purple, and a brand rule nobody can eyeball is a brand rule that erodes.
///
/// `system` is the default and means `NSColor.controlAccentColor` — the accent the *user* chose in
/// System Settings. That one is deliberately not audited here: if they picked purple for their own
/// Mac, that is their decision about their machine, and overriding it would be the same
/// brand-imposition Phase 0 removed. INV-UI-1 governs what this app ships, which is this list.
enum AccentChoice: String, CaseIterable, Identifiable, Codable, Sendable {
    case system
    case blue
    case teal
    case green
    case yellow
    case orange
    case red
    case graphite

    var id: String { rawValue }

    var title: String {
        switch self {
        case .system: "System"
        case .blue: "Azure"
        case .teal: "Teal"
        case .green: "Green"
        case .yellow: "Yellow"
        case .orange: "Orange"
        case .red: "Red"
        case .graphite: "Graphite"
        }
    }

    /// Nil for `system`, whose colour is not this file's to name.
    var nsColor: NSColor? {
        switch self {
        case .system: nil
        case .blue: .systemBlue
        case .teal: .systemTeal
        case .green: .systemGreen
        case .yellow: .systemYellow
        case .orange: .systemOrange
        case .red: .systemRed
        case .graphite: .systemGray
        }
    }

    /// The colour to actually paint with. Falls back to the user's own accent, which is what
    /// `Ink.accent` already is, so `system` changes nothing anywhere.
    var color: Color {
        Color(nsColor: nsColor ?? .controlAccentColor)
    }

    /// The named choices, i.e. everything this app is responsible for the hue of.
    static var named: [AccentChoice] { allCases.filter { $0 != .system } }
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
    var subtitle: String {
        switch self {
        case .best: "2400 px on the longest side · sharpest text, largest files"
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
enum StorageStrategy: String, CaseIterable, Identifiable, Codable, Sendable {
    case off
    case compress
    case limit

    var id: String { rawValue }

    var title: String {
        switch self {
        case .off: "Off"
        case .compress: "Compress"
        case .limit: "Limit"
        }
    }

    var subtitle: String {
        switch self {
        case .off: "Keep all your data. Forever."
        case .compress: "Compress older data."
        case .limit: "Limit Storage. Delete oldest recordings when threshold is reached."
        }
    }

    var symbol: String {
        switch self {
        case .off: "pause.circle"
        case .compress: "arrow.down.right.and.arrow.up.left"
        case .limit: "trash"
        }
    }

    /// True for anything that irreversibly changes what is already on disk.
    ///
    /// `limit` deletes recordings outright; `compress` re-encodes them lossily and the original
    /// pixels do not come back. Neither may be reachable by one stray click on a radio button.
    var destroysExistingData: Bool {
        switch self {
        case .off: false
        case .compress, .limit: true
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

/// Where ⌘↵ sends a query.
///
/// Only surfaces this app can genuinely reach are listed. `ClaudeRegistrar` writes the MCP entry for
/// Claude Code and Claude Desktop, so those two are real; anything else would be a menu item that
/// routes nowhere.
enum AgentRoute: String, CaseIterable, Identifiable, Codable, Sendable {
    case claudeCode
    case claudeDesktop

    var id: String { rawValue }

    var title: String {
        switch self {
        case .claudeCode: "Claude Code"
        case .claudeDesktop: "Claude Desktop"
        }
    }
}

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
        static let accent = "context.settings.accent"
        static let showsDockIcon = "context.settings.showsDockIcon"
        static let timelineControls = "context.settings.timelineControls"
        static let screenCapture = "context.settings.screenCapture"
        static let pausesOnInactivity = "context.settings.pausesOnInactivity"
        static let captureQuality = "context.settings.captureQuality"
        static let storageStrategy = "context.settings.storageStrategy"
        static let storageLimitBytes = "context.settings.storageLimitBytes"
        static let agentRoute = "context.settings.agentRoute"
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

    @Published var accent: AccentChoice {
        didSet {
            guard accent != oldValue else { return }
            defaults.set(accent.rawValue, forKey: Key.accent)
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

    @Published var agentRoute: AgentRoute {
        didSet {
            guard agentRoute != oldValue else { return }
            defaults.set(agentRoute.rawValue, forKey: Key.agentRoute)
        }
    }

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
        self.accent = enumValue(Key.accent, AccentChoice.system)
        // **Off** by default, which is a deliberate divergence from the reference's "toggle, on".
        // This app is `LSUIElement` and `ContextAppDelegate` calls appearing in the Dock "the single
        // most visible way this product could stop being ambient". Defaulting the preference on would
        // put the icon in the Dock the first time this store is constructed — i.e. the row's default
        // would silently undo the app's own design. The row still works in both directions.
        self.showsDockIcon = flag(Key.showsDockIcon, default: false)
        if let data = defaults.data(forKey: Key.timelineControls),
            let decoded = try? JSONDecoder().decode(TimelineControlVisibility.self, from: data)
        {
            self.timelineControls = decoded
        } else {
            self.timelineControls = TimelineControlVisibility()
        }
        self.screenCaptureEnabled = flag(Key.screenCapture, default: true)
        self.pausesOnInactivity = flag(Key.pausesOnInactivity, default: true)
        self.captureQuality = enumValue(Key.captureQuality, CaptureQuality.default)
        self.storage = StorageSelection(strategy: enumValue(Key.storageStrategy, StorageStrategy.off))
        let storedLimit = defaults.object(forKey: Key.storageLimitBytes) as? Int
        self.storageLimitBytes = StorageLimit.clamp(Int64(storedLimit ?? Int(StorageLimit.defaultBytes)))
        self.agentRoute = enumValue(Key.agentRoute, AgentRoute.claudeCode)
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

    var accentColor: Color { accent.color }

    /// What the Storage header says beside the measured usage.
    var storageLimitSummary: String {
        switch storage.strategy {
        case .off: "no storage limits set"
        case .compress: "older data set to compress"
        case .limit: "limited to \(StorageLimit.format(storageLimitBytes))"
        }
    }

    // MARK: Application

    private func applyAppearance() {
        guard appliesToRunningApp, NSApp != nil else { return }
        NSApp.appearance = appearance.nsAppearance
    }

    /// `LSUIElement` starts the process as `.accessory`. Flipping to `.regular` puts the icon in the
    /// Dock for this launch, which is what the row promises — and it takes effect immediately rather
    /// than at relaunch, so the row does not need a caveat.
    private func applyDockIcon() {
        guard appliesToRunningApp, NSApp != nil else { return }
        NSApp.setActivationPolicy(showsDockIcon ? .regular : .accessory)
    }
}

// MARK: - Version

/// The real version, from the bundle that is running.
///
/// There is no updater in this package, so this is the whole Updates row — see
/// `docs/requirements-checklist.md` I7 and `SettingsGeneralPane` for why `Update Now` and
/// `Automatic Updates` are absent rather than disabled.
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
