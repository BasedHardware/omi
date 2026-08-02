import AppKit
import Carbon.HIToolbox
import ContextCore
import Foundation

// MARK: - Modifiers

/// The four modifiers a chord can involve. `capsLock` and `fn` are deliberately absent: neither is
/// something a user thinks of as part of a shortcut, and both arrive in `flagsChanged` for reasons
/// that have nothing to do with the keys being pressed (a stuck Caps Lock, a Touch Bar mode change).
struct ShortcutModifiers: OptionSet, Hashable, Sendable {
    let rawValue: Int

    static let command = ShortcutModifiers(rawValue: 1 << 0)
    static let shift = ShortcutModifiers(rawValue: 1 << 1)
    static let option = ShortcutModifiers(rawValue: 1 << 2)
    static let control = ShortcutModifiers(rawValue: 1 << 3)

    /// Only the four that matter, so a Caps Lock or Fn change can never look like a chord change.
    init(_ flags: NSEvent.ModifierFlags) {
        var result: ShortcutModifiers = []
        if flags.contains(.command) { result.insert(.command) }
        if flags.contains(.shift) { result.insert(.shift) }
        if flags.contains(.option) { result.insert(.option) }
        if flags.contains(.control) { result.insert(.control) }
        self = result
    }

    init(rawValue: Int) { self.rawValue = rawValue }

    /// Apple's order: ⌃⌥⇧⌘, which is the order every macOS menu prints them in.
    var display: String {
        var out = ""
        if contains(.control) { out += "⌃" }
        if contains(.option) { out += "⌥" }
        if contains(.shift) { out += "⇧" }
        if contains(.command) { out += "⌘" }
        return out
    }

    var carbonFlags: UInt32 {
        var out: UInt32 = 0
        if contains(.command) { out |= UInt32(cmdKey) }
        if contains(.shift) { out |= UInt32(shiftKey) }
        if contains(.option) { out |= UInt32(optionKey) }
        if contains(.control) { out |= UInt32(controlKey) }
        return out
    }

    var appKitFlags: NSEvent.ModifierFlags {
        var out: NSEvent.ModifierFlags = []
        if contains(.command) { out.insert(.command) }
        if contains(.shift) { out.insert(.shift) }
        if contains(.option) { out.insert(.option) }
        if contains(.control) { out.insert(.control) }
        return out
    }
}

// MARK: - Chords

/// A shortcut, in a shape that can be compared against another product's binding.
///
/// Deliberately *not* a key code for the ordinary case. Comparing our binding to Codex's
/// `"CmdOrCtrl+Shift+K"` or Claude's `"double-tap-option"` has to happen on something both sides can
/// express, and a virtual key code is neither portable across layouts nor recoverable from an
/// accelerator string. The printed key label is.
enum ShortcutChord: Equatable, Hashable, Sendable {
    /// One modifier tapped twice, optionally with others held down throughout. `⌘⌘` is
    /// `.doubleTap(.command, alsoHeld: [])`; `⌘⌘⇧` is `.doubleTap(.command, alsoHeld: [.shift])`.
    case doubleTap(ShortcutModifiers, alsoHeld: ShortcutModifiers)
    /// An ordinary key equivalent. `label` is upper-cased and layout-independent-ish: whatever the
    /// key prints without modifiers, or a name like `SPACE` for keys that print nothing.
    case key(label: String, modifiers: ShortcutModifiers)

    var display: String {
        switch self {
        case .doubleTap(let tapped, let held):
            // The tapped modifier twice, then whatever is held — "⌘⌘⇧", which is how the reference
            // writes it.
            return tapped.display + tapped.display + held.display
        case .key(let label, let modifiers):
            return modifiers.display + label
        }
    }
}

// MARK: - The tap detector

/// The double-tap rules, as a value.
///
/// Split out from the event plumbing on purpose: "two Command presses inside 380 ms with nothing in
/// between" is the whole feature, and it is the part that can be wrong in ways no amount of clicking
/// around would reveal. Feeding it synthetic snapshots is the only way to assert what happens when
/// someone types ⌘C twice quickly, or holds ⌘ for a second, or taps ⌘ then adds Shift.
///
/// Fires on the **second release**, not the second press. Firing on the press is a few tens of
/// milliseconds quicker and wrong: `⌘` down, `⌘` down again and *held* is the opening of ⌘S, and a
/// timeline window that opens on its way there is worse than one that opens 40 ms later.
struct ModifierDoubleTap {
    /// Between the two presses. The reference calls for 350–400 ms; 380 is the middle of that, and
    /// comfortably below the ~500 ms at which two deliberate taps stop feeling like one gesture.
    static let maxGap: TimeInterval = 0.380
    /// A press held longer than this is a hold, not a tap — holding ⌘ is how macOS shows menu
    /// shortcut hints, and it must never count.
    static let maxHold: TimeInterval = 0.400

    /// One `flagsChanged`, reduced to what the rules need. `at` is monotonic (`NSEvent.timestamp`).
    struct Snapshot: Equatable {
        let modifiers: ShortcutModifiers
        let at: TimeInterval

        init(modifiers: ShortcutModifiers, at: TimeInterval) {
            self.modifiers = modifiers
            self.at = at
        }
    }

    /// The modifier being watched for a double tap.
    private let tapped: ShortcutModifiers

    // The press currently in flight, if the modifier is down.
    private var pressBeganAt: TimeInterval?
    private var pressHeld: ShortcutModifiers = []
    private var pressIsClean = true

    // The last press that completed as a clean tap, and is still eligible to be the first half.
    private var firstTapBeganAt: TimeInterval?
    private var firstTapHeld: ShortcutModifiers = []

    private var wasDown = false

    init(tapped: ShortcutModifiers = .command) {
        self.tapped = tapped
    }

    /// - Returns: the modifiers held alongside the tapped one when a double tap completes, or `nil`.
    mutating func flagsChanged(_ snapshot: Snapshot) -> ShortcutModifiers? {
        let isDown = snapshot.modifiers.contains(tapped)
        let held = snapshot.modifiers.subtracting(tapped)
        defer { wasDown = isDown }

        if isDown, !wasDown {
            // Press.
            pressBeganAt = snapshot.at
            pressHeld = held
            pressIsClean = true
            return nil
        }

        if !isDown, wasDown {
            // Release.
            let began = pressBeganAt
            pressBeganAt = nil
            guard let began,
                pressIsClean,
                // A tap has to be short, and the modifiers held around it have to be the same at
                // both ends — ⌘ down, then Shift added, then ⌘ up is not a chord anyone is aiming at.
                snapshot.at - began <= Self.maxHold,
                held == pressHeld
            else {
                forgetHistory()
                return nil
            }

            if let firstBegan = firstTapBeganAt,
                firstTapHeld == held,
                began - firstBegan <= Self.maxGap {
                forgetHistory()
                return held
            }

            firstTapBeganAt = began
            firstTapHeld = held
            return nil
        }

        // A modifier changed while the tapped one was down (or while nothing was down). Changing the
        // held set mid-press is what disqualifies ⌘ → ⌘⇧ from reading as either chord.
        if isDown, held != pressHeld {
            pressIsClean = false
        }
        return nil
    }

    /// Any ordinary key going down. `⌘C ⌘C` typed quickly is two presses inside the window, and the
    /// only thing that tells it apart from `⌘⌘` is that a key happened in between.
    mutating func keyPressed() {
        pressIsClean = false
        forgetHistory()
    }

    /// Drops every bit of in-flight state. Called when monitoring restarts, because the modifier may
    /// have gone up while we were not watching and `wasDown` would then be a lie.
    mutating func reset() {
        pressBeganAt = nil
        pressHeld = []
        pressIsClean = true
        wasDown = false
        forgetHistory()
    }

    private mutating func forgetHistory() {
        firstTapBeganAt = nil
        firstTapHeld = []
    }
}

// MARK: - Global shortcuts

/// The two system-wide shortcuts, and the honest truth about whether they are armed.
///
/// Two mechanisms, because the two kinds of binding are not the same problem:
///
/// - **The double-tap defaults** (`⌘⌘`, `⌘⌘⇧`) cannot be registered as hot keys at all. A modifier
///   tapped twice is not a key equivalent, so `RegisterEventHotKey` has nothing to take; the only
///   route is watching `flagsChanged` across the whole system, which macOS gates behind
///   Accessibility. When that grant is missing the shortcut does not fire, and `readiness(for:)`
///   says so rather than letting Settings imply otherwise.
/// - **A recorded key equivalent** goes through `RegisterEventHotKey`, which needs no permission at
///   all. So a user who rebinds the shortcut gets one that works on a machine where Accessibility
///   was refused — and, just as importantly, the app stops observing every keystroke on the system
///   the moment it no longer needs to.
///
/// Nothing here consumes an event. The monitors are observers; a Carbon hot key is exclusive by
/// design, which is what makes conflict detection (`ShortcutConflicts`) worth doing at all.
@MainActor
final class GlobalShortcuts {
    static let shared = GlobalShortcuts()

    // MARK: Actions

    enum Action: String, CaseIterable, Sendable {
        case openTimeline
        case openSearch

        /// The Settings row title, verbatim from the reference's General pane.
        var title: String {
            switch self {
            case .openTimeline: return "Open Timeline Shortcut"
            case .openSearch: return "Open Search Shortcut"
            }
        }

        /// The reference's subtitle, with our own default spelled out — the copy is what tells the
        /// user that clearing the recorder is a real choice and not a broken state.
        var subtitle: String {
            "Record a keyboard shortcut. Clear it to use \(defaultChord.display)."
        }

        /// `⌘⌘` for the timeline, `⌘⌘⇧` for search.
        var defaultChord: ShortcutChord {
            switch self {
            case .openTimeline: return .doubleTap(.command, alsoHeld: [])
            case .openSearch: return .doubleTap(.command, alsoHeld: [.shift])
            }
        }

        fileprivate var defaultHeld: ShortcutModifiers {
            switch self {
            case .openTimeline: return []
            case .openSearch: return [.shift]
            }
        }

        /// Stable, small, and never zero — Carbon hot key ids are `UInt32` and 0 is a legal id we
        /// would not be able to tell from an uninitialised struct.
        fileprivate var hotKeyID: UInt32 {
            switch self {
            case .openTimeline: return 1
            case .openSearch: return 2
            }
        }

        /// Namespaced the way every other persisted value in this app is (see `Permissions.Key`).
        var storageKey: String {
            "context.shortcut.\(rawValue).keyEquivalent"
        }
    }

    /// A shortcut the user recorded. `label` is captured at record time from the event itself, so it
    /// is what that key prints on *their* layout rather than what it would print on a US one.
    struct Recorded: Equatable, Sendable {
        var keyCode: UInt16
        var modifiers: ShortcutModifiers
        var label: String

        var chord: ShortcutChord { .key(label: label, modifiers: modifiers) }
    }

    enum Binding: Equatable, Sendable {
        case doubleTapDefault
        case recorded(Recorded)
    }

    /// What Settings is allowed to claim.
    enum Readiness: Equatable, Sendable {
        /// Registered, and it will fire.
        case armed
        /// A double-tap binding with no Accessibility grant. The shortcut does nothing; the row has
        /// to say that and offer the pane.
        case needsAccessibility
        /// Registration was refused — almost always because something else on the machine already
        /// owns this exact key equivalent.
        case rejected(String)
    }

    // MARK: Storage

    /// Where a recorded binding lives.
    ///
    /// Split out from the class so the persistence rules — above all "nothing stored means the
    /// double-tap default", which is the whole of the reference's "Clear it to use ⌘⌘" — can be
    /// asserted without registering a system-wide hot key from a test process.
    struct Store {
        let defaults: UserDefaults

        init(defaults: UserDefaults = .standard) {
            self.defaults = defaults
        }

        func binding(for action: Action) -> Binding {
            guard let stored = defaults.dictionary(forKey: action.storageKey),
                let keyCode = stored["keyCode"] as? Int,
                let modifiers = stored["modifiers"] as? Int,
                let label = stored["label"] as? String,
                !label.isEmpty
            else {
                return .doubleTapDefault
            }
            return .recorded(
                Recorded(
                    keyCode: UInt16(truncatingIfNeeded: keyCode),
                    modifiers: ShortcutModifiers(rawValue: modifiers),
                    label: label))
        }

        func chord(for action: Action) -> ShortcutChord {
            switch binding(for: action) {
            case .doubleTapDefault: return action.defaultChord
            case .recorded(let recorded): return recorded.chord
            }
        }

        /// `nil` clears the binding, which is exactly what the reference's copy promises.
        func setRecorded(_ recorded: Recorded?, for action: Action) {
            guard let recorded else {
                defaults.removeObject(forKey: action.storageKey)
                return
            }
            defaults.set(
                [
                    "keyCode": Int(recorded.keyCode),
                    "modifiers": recorded.modifiers.rawValue,
                    "label": recorded.label,
                ],
                forKey: action.storageKey)
        }
    }

    // MARK: State

    private let store: Store
    private var detector = ModifierDoubleTap()
    private var globalMonitor: Any?
    private var localMonitor: Any?
    private var hotKeys: [Action: EventHotKeyRef] = [:]
    private var rejections: [Action: String] = [:]
    private var onTrigger: ((Action) -> Void)?
    private var carbonHandler: EventHandlerRef?
    private var activationObserver: NSObjectProtocol?

    init(store: Store = Store()) {
        self.store = store
    }

    // MARK: Bindings

    func binding(for action: Action) -> Binding { store.binding(for: action) }

    func chord(for action: Action) -> ShortcutChord { store.chord(for: action) }

    /// What the recorder shows. Never blank: a cleared binding shows the double-tap default, because
    /// that is what will actually happen.
    func display(for action: Action) -> String { chord(for: action).display }

    func setRecorded(_ recorded: Recorded?, for action: Action) {
        store.setRecorded(recorded, for: action)
        rejections[action] = nil
        // Re-registering both is cheaper than reasoning about which half moved, and it is the only
        // way a newly cleared binding gets the monitor back.
        reapply()
    }

    /// The chords that are live right now, for `ShortcutConflicts`. Only bindings that are actually
    /// armed appear: a chord we failed to register is not a chord anyone else can conflict with.
    func armedChords() -> [Action: ShortcutChord] {
        var out: [Action: ShortcutChord] = [:]
        for action in Action.allCases where readiness(for: action) == .armed {
            out[action] = chord(for: action)
        }
        return out
    }

    // MARK: Readiness

    func readiness(for action: Action) -> Readiness {
        if let reason = rejections[action] { return .rejected(reason) }
        switch binding(for: action) {
        case .doubleTapDefault:
            return AXElement.isTrusted ? .armed : .needsAccessibility
        case .recorded:
            return hotKeys[action] != nil ? .armed : .rejected("macOS refused this shortcut.")
        }
    }

    /// True when any binding still needs Accessibility. The one thing Settings needs for a summary
    /// line, without asking about each row.
    var needsAccessibility: Bool {
        Action.allCases.contains { readiness(for: $0) == .needsAccessibility }
    }

    // MARK: Lifecycle

    /// Registers everything and starts delivering. Idempotent.
    func start(onTrigger: @escaping (Action) -> Void) {
        self.onTrigger = onTrigger
        observeActivation()
        reapply()
    }

    /// Re-evaluates permission and re-registers. Accessibility can be granted while the app runs and
    /// macOS posts nothing when it happens, so this is what Settings calls when it appears — and
    /// what the activation observer calls when the user comes back from the Accessibility pane.
    func refresh() {
        reapply()
    }

    func stop() {
        removeMonitors()
        for (_, ref) in hotKeys { UnregisterEventHotKey(ref) }
        hotKeys = [:]
        if let carbonHandler {
            RemoveEventHandler(carbonHandler)
            self.carbonHandler = nil
        }
        if let activationObserver {
            NotificationCenter.default.removeObserver(activationObserver)
            self.activationObserver = nil
        }
    }

    // MARK: Registration

    private func reapply() {
        // Hot keys first: a rejection there is what the monitor decision below must not paper over.
        for (_, ref) in hotKeys { UnregisterEventHotKey(ref) }
        hotKeys = [:]

        var wantsMonitor = false
        for action in Action.allCases {
            switch binding(for: action) {
            case .doubleTapDefault:
                wantsMonitor = true
            case .recorded(let recorded):
                register(recorded, for: action)
            }
        }

        if wantsMonitor, AXElement.isTrusted {
            installMonitors()
        } else {
            removeMonitors()
        }
    }

    private func register(_ recorded: Recorded, for action: Action) {
        installCarbonHandlerIfNeeded()
        var ref: EventHotKeyRef?
        let id = EventHotKeyID(signature: Self.signature, id: action.hotKeyID)
        let status = RegisterEventHotKey(
            UInt32(recorded.keyCode), recorded.modifiers.carbonFlags, id, GetApplicationEventTarget(), 0, &ref)
        if status == noErr, let ref {
            hotKeys[action] = ref
            rejections[action] = nil
            ContextLog.info("Registered \(action.rawValue) as \(recorded.chord.display)", Self.logCategory)
        } else {
            // The overwhelmingly likely cause is that something else on the machine already holds
            // this exact chord. Saying so is more useful than an OSStatus.
            rejections[action] = "Something else on this Mac already uses \(recorded.chord.display)."
            ContextLog.error(
                "Could not register \(action.rawValue) as \(recorded.chord.display) (OSStatus \(status))",
                Self.logCategory)
        }
    }

    private func installMonitors() {
        guard globalMonitor == nil, localMonitor == nil else { return }
        detector.reset()

        // Passive: a global monitor cannot alter or swallow an event, which is the property that
        // keeps ⌘ behaving like ⌘ in every other app on the machine.
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.flagsChanged, .keyDown]) { event in
            MainActor.assumeIsolated { GlobalShortcuts.shared.observe(event) }
        }
        // A global monitor never sees events delivered to our own process, so without this the
        // shortcut would die the moment one of our own windows had focus — including the search bar
        // it opens.
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: [.flagsChanged, .keyDown]) { event in
            MainActor.assumeIsolated { GlobalShortcuts.shared.observe(event) }
            return event
        }
        ContextLog.info("Watching flagsChanged for the double-tap defaults", Self.logCategory)
    }

    private func removeMonitors() {
        if let globalMonitor { NSEvent.removeMonitor(globalMonitor) }
        if let localMonitor { NSEvent.removeMonitor(localMonitor) }
        globalMonitor = nil
        localMonitor = nil
        detector.reset()
    }

    /// Accessibility is granted in System Settings, and the only reliable signal that it happened is
    /// the user coming back to us.
    private func observeActivation() {
        guard activationObserver == nil else { return }
        activationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { _ in
            MainActor.assumeIsolated { GlobalShortcuts.shared.refresh() }
        }
    }

    // MARK: Delivery

    fileprivate func observe(_ event: NSEvent) {
        switch event.type {
        case .flagsChanged:
            let snapshot = ModifierDoubleTap.Snapshot(
                modifiers: ShortcutModifiers(event.modifierFlags), at: event.timestamp)
            guard let held = detector.flagsChanged(snapshot) else { return }
            fireDoubleTap(held: held)
        case .keyDown:
            detector.keyPressed()
        default:
            break
        }
    }

    private func fireDoubleTap(held: ShortcutModifiers) {
        // Only an action still on its default answers to a double tap. Rebinding the timeline to
        // ⌥Space and leaving search on ⌘⌘⇧ must not leave ⌘⌘ opening the timeline as well.
        guard let action = Action.allCases.first(where: {
            binding(for: $0) == .doubleTapDefault && $0.defaultHeld == held
        }) else { return }
        deliver(action)
    }

    fileprivate func hotKeyFired(id: UInt32) {
        guard let action = Action.allCases.first(where: { $0.hotKeyID == id }) else { return }
        deliver(action)
    }

    private func deliver(_ action: Action) {
        ContextLog.info("\(action.rawValue) fired via \(chord(for: action).display)", Self.logCategory)
        onTrigger?(action)
    }

    // MARK: Carbon plumbing

    private static let logCategory = "shortcuts"
    /// `'CtxS'`. Carbon signatures are four-char codes and the value only has to be ours.
    private static let signature: OSType = 0x4374_7853

    private func installCarbonHandlerIfNeeded() {
        guard carbonHandler == nil else { return }
        var spec = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        var ref: EventHandlerRef?
        // The handler is a C function pointer, so it cannot capture — it reads the id out of the
        // event and hands it to the singleton on the main actor.
        let status = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, _ -> OSStatus in
                guard let event else { return OSStatus(eventNotHandledErr) }
                var id = EventHotKeyID()
                let read = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &id)
                guard read == noErr, id.signature == GlobalShortcuts.signature else {
                    return OSStatus(eventNotHandledErr)
                }
                let hotKeyID = id.id
                DispatchQueue.main.async {
                    MainActor.assumeIsolated { GlobalShortcuts.shared.hotKeyFired(id: hotKeyID) }
                }
                return noErr
            },
            1,
            &spec,
            nil,
            &ref)
        if status == noErr {
            carbonHandler = ref
        } else {
            ContextLog.error("Could not install the hot key handler (OSStatus \(status))", Self.logCategory)
        }
    }
}

// MARK: - Recording

extension GlobalShortcuts.Recorded {
    /// Builds a binding out of the event a recorder captured, or `nil` when the press is not a
    /// shortcut anyone can use.
    ///
    /// Rejected on purpose:
    /// - **A bare key.** `T` as a system-wide shortcut would eat the letter T everywhere.
    /// - **Shift alone.** `⇧T` is `T`, so it eats a letter too.
    /// - **Escape and Return.** Both mean something specific in every app on the machine.
    static func from(_ event: NSEvent) -> GlobalShortcuts.Recorded? {
        guard event.type == .keyDown else { return nil }
        let modifiers = ShortcutModifiers(event.modifierFlags)
        guard !modifiers.subtracting(.shift).isEmpty else { return nil }
        let reserved: Set<UInt16> = [UInt16(kVK_Escape), UInt16(kVK_Return), UInt16(kVK_ANSI_KeypadEnter)]
        guard !reserved.contains(event.keyCode) else { return nil }
        return GlobalShortcuts.Recorded(
            keyCode: event.keyCode, modifiers: modifiers, label: label(for: event))
    }

    /// What the key prints, upper-cased, or a name for the keys that print nothing legible.
    private static func label(for event: NSEvent) -> String {
        if let named = namedKeys[event.keyCode] { return named }
        let characters = event.charactersIgnoringModifiers ?? ""
        let trimmed = characters.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return "Key \(event.keyCode)" }
        return trimmed.uppercased()
    }

    /// Only the keys whose printed form is blank or misleading. Everything else comes from the event.
    private static let namedKeys: [UInt16: String] = [
        UInt16(kVK_Space): "Space",
        UInt16(kVK_Tab): "⇥",
        UInt16(kVK_Delete): "⌫",
        UInt16(kVK_ForwardDelete): "⌦",
        UInt16(kVK_LeftArrow): "←",
        UInt16(kVK_RightArrow): "→",
        UInt16(kVK_UpArrow): "↑",
        UInt16(kVK_DownArrow): "↓",
        UInt16(kVK_Home): "↖",
        UInt16(kVK_End): "↘",
        UInt16(kVK_PageUp): "⇞",
        UInt16(kVK_PageDown): "⇟",
    ]
}
