import AppKit
import ApplicationServices
import SwiftUI

//  The permission choreography: what we may draw, what we may only point at, and the one line
//  between the two that this file exists to hold.
//
//  **macOS draws the affordance, not us.** On macOS 26 the dashed row and the "Drag this row up
//  into the list" arrow inside Privacy & Security are System Settings' own UI. No application can
//  draw inside another application's window, and no application should pretend to: a replica of
//  someone else's control, presented where theirs would be, is a forgery whether or not it was
//  meant as one. So the choreography is two distinct acts, and they never blur:
//
//  1. **On our card**, `GhostRowReplica` plays a small animation of a ghost row rising into a list.
//     It is ours, it is obviously ours, and it is captioned as a preview. Its whole job is that the
//     real thing is recognised a second later rather than met cold.
//  2. **Over System Settings**, `PermissionOverlay` finds the *real* row through the Accessibility
//     API and rings it. It draws nothing that belongs to System Settings — a ring outside the row
//     and a hand beside it, both plainly ours, both pointing at their UI rather than replacing it.
//
//  And the rule that governs act 2: **a confident arrow aimed at nothing is worse than a
//  sentence.** The lookup fails for ordinary reasons — Accessibility itself is not granted yet, the
//  list is scrolled, the pane relaid out on a macOS we have not seen. Every one of those degrades
//  to `PermissionGuidance.instruction`: words, no ring, no hand, nothing aimed anywhere.

// MARK: - What the choreography is allowed to say

/// The only two things the overlay can be. There is deliberately no third case that points
/// "approximately" — the type is what makes a mispositioned ring unrepresentable.
enum PermissionGuidance: Equatable {
    /// The real row was located and is really on screen. Screen coordinates, top-left origin, the
    /// convention the Accessibility API and CoreGraphics both use.
    case pointing(LocatedSettingsRow)
    /// The row could not be located, or was located somewhere the user cannot see. Words only.
    case instruction(String)

    /// True only for the case that draws a ring. Reads better than a pattern match at call sites
    /// whose only question is whether anything is being aimed.
    var isPointing: Bool {
        if case .pointing = self { return true }
        return false
    }
}

/// A located row in System Settings: what to ring, what the hand points at, and whether the switch
/// is already on.
struct LocatedSettingsRow: Equatable {
    /// The whole row — label through switch. What the ring goes around.
    var row: CGRect
    /// The switch itself. What the hand points at, because it is the thing to press.
    var toggle: CGRect
    /// The switch's current state, read from the same element. A row that is already on needs no
    /// hand, so the caller can stop rather than instruct someone to do what they have done.
    var isOn: Bool
}

// MARK: - The element the locator walks

/// The narrow view of an accessibility element the locator needs.
///
/// `AXElement` is the app's AX wrapper and is used here for the one question it can answer about
/// this problem — `AXElement.isTrusted`, the precondition for any of this working at all. It cannot
/// answer the rest: it is a *text capture* type by design ("makes no policy decisions … only
/// answers questions") and deliberately exposes no geometry and no `AXIdentifier`, and it keeps its
/// `AXUIElement` private so geometry cannot be recovered from one. Rather than widen a type three
/// other call sites depend on, the locator declares the shape it needs and `LiveSettingsElement`
/// implements it — which is also what lets the whole lookup be tested against a fake tree, with no
/// System Settings and no grant.
protocol SettingsElement {
    var elementRole: String? { get }
    /// System Settings' own `AXIdentifier`. Undocumented, and therefore never load-bearing on its
    /// own — see `SettingsRowLocator` for the fallback that runs when it is absent.
    var elementIdentifier: String? { get }
    var elementValue: String? { get }
    /// Screen coordinates, top-left origin. `nil` for an element that does not answer geometry.
    var elementFrame: CGRect? { get }
    var elementChildren: [any SettingsElement] { get }
}

// MARK: - Finding the real row

/// Finds one application's row inside a Privacy & Security pane.
///
/// Measured against macOS 26.5.2 (build 25F84), where the two pane shapes are genuinely different
/// and a locator that assumed either one alone would miss half the time:
///
/// - **Microphone** is flat: `AXStaticText` and `AXCheckBox` as sibling leaves of one group.
/// - **Screen & System Audio Recording** and **Accessibility** are outlines:
///   `AXRow` → `AXCell` → (`AXStaticText`, `AXCheckBox`).
///
/// What both shapes share is System Settings' own identifiers on the two leaves —
/// `"<App Name>_Title"` and `"<App Name>_Toggle"` — so those are the primary handle, and matching
/// the label's *text* is the fallback for the day they change. Neither is trusted blindly: the
/// result is only ever returned with a frame that was really read off the element.
struct SettingsRowLocator {
    /// The name System Settings lists us under: `CFBundleName`, which is what builds the identifier.
    let appName: String
    var limits = Limits()

    /// Ceilings, for the same reason `AccessibilityTree` has them: an application can answer AX
    /// queries slowly and claim any number of children, and this runs while the user is waiting.
    struct Limits {
        var maxDepth = 18
        var maxNodes = 4_000
    }

    /// Where a row can be.
    ///
    /// `offscreen` is a separate case rather than folded into `notFound` because the two deserve
    /// different sentences: one asks the user to scroll, the other cannot say where to look at all.
    /// Both refuse to point.
    enum Location: Equatable {
        case visible(LocatedSettingsRow)
        /// Found in the tree, but clipped out of view by a scroll area or the window edge.
        case offscreen(LocatedSettingsRow)
        case notFound
    }

    private var titleIdentifier: String { "\(appName)_Title" }
    private var toggleIdentifier: String { "\(appName)_Toggle" }

    /// Walks `root` for our row.
    ///
    /// `preferring` picks between the several sections a pane can have — the Screen Recording pane
    /// on macOS 26 lists us **twice**, once under "Screen & System Audio Recording" and again under
    /// "System Audio Recording Only", and ringing the wrong one is exactly the mispositioned arrow
    /// this whole file is arranged to avoid. Ordinal, not by header text: the header is a sibling of
    /// the section rather than its ancestor, so there is no containment relation to search, and the
    /// order of the sections is stable where their wording is not.
    func locate(in root: any SettingsElement, preferring occurrence: Int = 0) -> Location {
        var state = Walk(limits: limits)
        var clips: [CGRect] = []
        if let frame = root.elementFrame { clips.append(frame) }
        walk(root, depth: 0, clips: clips, state: &state)

        guard !state.hits.isEmpty else { return .notFound }
        let index = min(max(occurrence, 0), state.hits.count - 1)
        let hit = state.hits[index]
        return hit.isClipped ? .offscreen(hit.located) : .visible(hit.located)
    }

    // MARK: The walk

    private struct Hit {
        var located: LocatedSettingsRow
        var isClipped: Bool
    }

    private struct Walk {
        let limits: Limits
        var nodesRemaining: Int
        var hits: [Hit] = []

        init(limits: Limits) {
            self.limits = limits
            nodesRemaining = limits.maxNodes
        }
    }

    /// One pass, carrying the clip stack down.
    ///
    /// The clip stack is every ancestor that can hide this element: the window, and every scroll
    /// area between it and here. A row scrolled out of a list still answers with a perfectly
    /// plausible frame — one that is nowhere the user can see — and pointing at it is the exact
    /// failure mode that makes an overlay worse than a sentence.
    private func walk(_ element: any SettingsElement, depth: Int, clips: [CGRect], state: inout Walk) {
        guard depth <= limits.maxDepth, state.nodesRemaining > 0 else { return }
        state.nodesRemaining -= 1

        var clips = clips
        if element.elementRole == kAXScrollAreaRole, let frame = element.elementFrame {
            clips.append(frame)
        }

        let children = element.elementChildren
        if let hit = row(in: element, children: children, clips: clips) {
            state.hits.append(hit)
            // No descent past a match: the row's own subtree cannot contain a second row, and
            // stopping keeps a nested outline from reporting the same switch twice.
            return
        }

        for child in children {
            walk(child, depth: depth + 1, clips: clips, state: &state)
        }
    }

    /// Whether `element` is the container of our row, and if so where.
    ///
    /// Reads the label and the switch out of the *same* container so the two halves can never come
    /// from different rows — a union of one app's label with the next app's switch would produce a
    /// ring that looks right and is wrong.
    private func row(in element: any SettingsElement, children: [any SettingsElement], clips: [CGRect]) -> Hit? {
        guard let toggle = children.first(where: isOurToggle), let toggleFrame = toggle.elementFrame
        else { return nil }

        let label = children.first(where: isOurLabel)?.elementFrame
        // The row is the label through the switch when the label answered, and the container's own
        // frame when it did not. Never the switch alone: a 36 × 16 ring on a 460 pt row reads as a
        // dot beside the thing instead of around it.
        let band = label.map { $0.union(toggleFrame) } ?? element.elementFrame ?? toggleFrame

        let located = LocatedSettingsRow(row: band, toggle: toggleFrame, isOn: isOn(toggle))
        let clipped = !clips.allSatisfy { $0.contains(toggleFrame) }
        return Hit(located: located, isClipped: clipped)
    }

    private func isOurToggle(_ element: any SettingsElement) -> Bool {
        guard element.elementRole == kAXCheckBoxRole else { return false }
        // The identifier when System Settings offers one. When it does not, any switch sitting
        // beside our label is ours — which is why this is only ever asked of a container that
        // already matched `isOurLabel`, never of the pane at large.
        return element.elementIdentifier == toggleIdentifier || element.elementIdentifier == nil
    }

    private func isOurLabel(_ element: any SettingsElement) -> Bool {
        guard element.elementRole == kAXStaticTextRole else { return false }
        return element.elementIdentifier == titleIdentifier || element.elementValue == appName
    }

    /// System Settings answers a switch's state as `"1"` / `"0"`, or as a bridged number.
    private func isOn(_ element: any SettingsElement) -> Bool {
        guard let value = element.elementValue else { return false }
        return value == "1" || value.lowercased() == "true"
    }
}

// MARK: - The real accessibility tree

/// `SettingsElement` over a live `AXUIElement`.
///
/// Every property is one synchronous message to System Settings, which is why the locator above is
/// bounded on depth and node count rather than trusting the tree to be small.
struct LiveSettingsElement: SettingsElement {
    private let element: AXUIElement

    init(_ element: AXUIElement) {
        self.element = element
    }

    /// System Settings' windows, or an empty array when it is not running, is not readable, or this
    /// process is not trusted. An empty array is what makes the locator degrade instead of throw.
    static func systemSettingsWindows(bundleID: String = "com.apple.systempreferences") -> [LiveSettingsElement] {
        guard AXElement.isTrusted else { return [] }
        guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first
        else { return [] }
        let axApp = AXUIElementCreateApplication(app.processIdentifier)
        guard let raw = copy(kAXWindowsAttribute, from: axApp),
            CFGetTypeID(raw) == CFArrayGetTypeID(),
            let array = raw as? [AnyObject]
        else { return [] }
        return array.compactMap { window in
            guard CFGetTypeID(window) == AXUIElementGetTypeID() else { return nil }
            return LiveSettingsElement(window as! AXUIElement)
        }
    }

    var elementRole: String? { string(kAXRoleAttribute) }
    var elementIdentifier: String? { string("AXIdentifier") }

    /// A switch answers `AXValue` as a number, not a string, so this cannot use the string-only read
    /// `AXElement` uses for text capture — there, a slider's position getting into the text index is
    /// the bug; here, the number *is* the answer.
    var elementValue: String? {
        guard let value = Self.copy(kAXValueAttribute, from: element) else { return nil }
        if CFGetTypeID(value) == CFStringGetTypeID() { return value as? String }
        if let number = value as? NSNumber { return number.intValue == 0 ? "0" : "1" }
        return nil
    }

    var elementFrame: CGRect? {
        guard let position = Self.copy(kAXPositionAttribute, from: element),
            let size = Self.copy(kAXSizeAttribute, from: element),
            CFGetTypeID(position) == AXValueGetTypeID(),
            CFGetTypeID(size) == AXValueGetTypeID()
        else { return nil }
        var origin = CGPoint.zero
        var extent = CGSize.zero
        guard AXValueGetValue(position as! AXValue, .cgPoint, &origin),
            AXValueGetValue(size as! AXValue, .cgSize, &extent)
        else { return nil }
        return CGRect(origin: origin, size: extent)
    }

    var elementChildren: [any SettingsElement] {
        guard let raw = Self.copy(kAXChildrenAttribute, from: element),
            CFGetTypeID(raw) == CFArrayGetTypeID(),
            let array = raw as? [AnyObject]
        else { return [] }
        return array.compactMap { child in
            guard CFGetTypeID(child) == AXUIElementGetTypeID() else { return nil }
            return LiveSettingsElement(child as! AXUIElement)
        }
    }

    private func string(_ attribute: String) -> String? {
        guard let value = Self.copy(attribute, from: element),
            CFGetTypeID(value) == CFStringGetTypeID()
        else { return nil }
        return value as? String
    }

    private static func copy(_ attribute: String, from element: AXUIElement) -> AnyObject? {
        var value: AnyObject?
        // Any error means "this element does not answer that", which is ordinary: not every element
        // has an identifier, and an application mid-relayout answers nothing at all.
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success
        else { return nil }
        return value
    }
}

// MARK: - Deciding what to say

/// Turns a capability into either a ring around the real row or a sentence, and never into a guess.
///
/// Split out from the overlay so the decision — the part with a wrong answer available — is testable
/// with no window server, no System Settings and no grant.
enum PermissionChoreography {
    /// Which of the pane's sections holds the row for this capability.
    ///
    /// This exists because the Screen Recording pane on macOS 26.5 lists an app **twice** — under
    /// "Screen & System Audio Recording" and again under "System Audio Recording Only" — so "the row
    /// for this app" is ambiguous there and ringing the wrong one is the mispositioned overlay
    /// arriving by an entirely plausible route. Every capability is 0 today, which is the point: the
    /// section is chosen by construction rather than by whichever match the walk happened to reach
    /// first.
    ///
    /// `systemAudio` is 0 rather than 1 despite the tap's switch also appearing in that second
    /// section, because the overlay opens `Capability.settingsPane` and that route sends system audio
    /// to the **Microphone** pane, which has a single list. Pointing at section 1 of a pane with one
    /// section would degrade to a sentence on a row that is right there.
    static func sectionOccurrence(for capability: Capability) -> Int {
        switch capability {
        case .microphone, .systemAudio, .screen, .accessibility: return 0
        }
    }

    /// What the user has to do in their own terms, for the case where we cannot show them.
    ///
    /// Names the pane and the row, because that is the whole of the instruction once the pointing
    /// is off the table.
    static func instruction(for capability: Capability, appName: String, scrolled: Bool) -> String {
        let place: String
        switch capability {
        case .microphone: place = "Privacy & Security ▸ Microphone"
        case .systemAudio: place = "Privacy & Security ▸ Screen & System Audio Recording"
        case .screen: place = "Privacy & Security ▸ Screen & System Audio Recording"
        case .accessibility: place = "Privacy & Security ▸ Accessibility"
        }
        if scrolled {
            return "Scroll down to \(appName) in \(place) and switch it on."
        }
        return "In System Settings, open \(place) and switch on \(appName)."
    }

    /// The decision, in one place.
    ///
    /// `windows` is passed in rather than read here so the whole thing runs against a fake tree.
    /// Every failure — not trusted, not running, not found, scrolled away, already on — comes out as
    /// an `instruction`, and only a row really on screen comes out as `pointing`.
    static func guidance(
        for capability: Capability,
        appName: String,
        windows: [any SettingsElement]
    ) -> PermissionGuidance {
        let locator = SettingsRowLocator(appName: appName)
        let occurrence = sectionOccurrence(for: capability)

        var sawScrolledRow = false
        for window in windows {
            switch locator.locate(in: window, preferring: occurrence) {
            case .visible(let located):
                return .pointing(located)
            case .offscreen:
                sawScrolledRow = true
            case .notFound:
                continue
            }
        }
        return .instruction(instruction(for: capability, appName: appName, scrolled: sawScrolledRow))
    }

    /// The live call. Reads System Settings' real windows and hands them to the decision above.
    ///
    /// Logs which way it went, because the hit rate of the lookup is the only honest measure of
    /// whether the overlay is worth showing — and it cannot be measured from a unit test, whose tree
    /// is a fixture by construction. `AXElement.isTrusted` is included in the line: much the most
    /// common reason to degrade is that Accessibility itself has not been granted yet, and a log that
    /// says "not found" without saying "and we were not allowed to look" sends the reader hunting for
    /// a layout change that is not there.
    static func liveGuidance(for capability: Capability) -> PermissionGuidance {
        let windows = LiveSettingsElement.systemSettingsWindows()
        let decision = guidance(for: capability, appName: appDisplayName, windows: windows)
        switch decision {
        case .pointing(let located):
            ContextLog.info(
                "choreography: pointing at the \(capability.rawValue) row at "
                    + "\(Int(located.row.minX)),\(Int(located.row.minY)) "
                    + "\(Int(located.row.width))x\(Int(located.row.height)), switch is "
                    + (located.isOn ? "on" : "off"),
                "permissions")
        case .instruction:
            ContextLog.info(
                "choreography: could not locate the \(capability.rawValue) row "
                    + "(trusted: \(AXElement.isTrusted), settings windows: \(windows.count)); "
                    + "showing the written instruction instead",
                "permissions")
        }
        return decision
    }

    /// Forces the choreography onto one capability, for a self-test that must not revoke a real
    /// grant to reach the code path.
    ///
    /// Read from the environment rather than compiled behind `#if DEBUG`, because the build worth
    /// testing is the signed release bundle. It changes nothing for anyone who does not set it, and
    /// it can only ever *show* the overlay — the grant still has to be given by hand in System
    /// Settings, exactly as it would be otherwise. `CONTEXT_CHOREOGRAPHY_PROBE=accessibility`.
    static var probedCapability: Capability? {
        guard let raw = ProcessInfo.processInfo.environment["CONTEXT_CHOREOGRAPHY_PROBE"] else { return nil }
        return Capability(rawValue: raw)
    }

    /// The name System Settings lists us under. `CFBundleName` and not a literal, so a rename cannot
    /// leave the locator hunting for a row that no longer carries that name.
    static var appDisplayName: String {
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String)
            ?? (Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String)
            ?? "Context for Claude"
    }
}

// MARK: - The overlay

/// A ring and a hand over the real row in System Settings, or a plain instruction panel when the
/// row cannot honestly be pointed at.
///
/// Built the same way `MenuBarSpotlight` is — a borderless, click-through window above the app being
/// pointed at — for the same reason: the user has to be able to press the thing we are pointing at,
/// so the overlay must never be in the way of it.
@MainActor
enum PermissionOverlay {
    private static var window: NSWindow?
    private static var tracker: Task<Void, Never>?
    private static var current: PermissionGuidance?

    /// How often the row is re-located while the overlay is up. The user scrolls the list, drags the
    /// window, switches panes — and a ring that stays where the row *was* is the mispositioned
    /// overlay arriving by a slower route.
    private static let trackInterval = Duration.milliseconds(400)
    /// Room around the row for the ring. The room below it for the hand belongs to the view that
    /// draws the hand, so the two cannot drift apart.
    private static let ringPadding: CGFloat = 8

    /// Shows the overlay for `capability` and keeps it correct until `hide()`.
    ///
    /// `resolve` is injectable only so this can be driven from a test or a probe; production passes
    /// the live lookup.
    static func show(
        for capability: Capability,
        caption: String,
        resolve: @escaping @MainActor (Capability) -> PermissionGuidance = PermissionChoreography.liveGuidance
    ) {
        tracker?.cancel()
        apply(resolve(capability), caption: caption)
        tracker = Task { @MainActor in
            while !Task.isCancelled {
                try? await Task.sleep(for: trackInterval)
                if Task.isCancelled { return }
                apply(resolve(capability), caption: caption)
            }
        }
    }

    /// Confirms the grant on the overlay before it goes, so the user sees the thing they just did
    /// land. A confirmation nobody witnesses is the same as none.
    static func confirmGranted(_ text: String = "Switched on.") {
        tracker?.cancel()
        tracker = nil
        guard let window, let view = window.contentView as? PermissionOverlayView else {
            hide()
            return
        }
        view.showConfirmation(text)
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(1_400))
            hide()
        }
    }

    static func hide() {
        tracker?.cancel()
        tracker = nil
        current = nil
        window?.orderOut(nil)
        window = nil
    }

    /// The guidance currently on screen. Exposed for the self-test probe, which reports the hit rate.
    static var showing: PermissionGuidance? { current }

    // MARK: Drawing

    private static func apply(_ guidance: PermissionGuidance, caption: String) {
        guard guidance != current || window == nil else { return }
        current = guidance

        switch guidance {
        case .pointing(let located):
            present(frame: overlayFrame(around: located.row), guidance: guidance, caption: caption)
        case .instruction:
            present(frame: instructionFrame(), guidance: guidance, caption: caption)
        }
    }

    /// The ring's window: the row plus room for the ring and the hand beneath it.
    private static func overlayFrame(around row: CGRect) -> NSRect {
        let box = CGRect(
            x: row.minX - ringPadding,
            y: row.minY - ringPadding,
            width: row.width + ringPadding * 2,
            height: row.height + ringPadding * 2 + PermissionOverlayView.handRoom)
        return flipped(box)
    }

    /// Where a sentence goes when there is nothing to point at: centred near the top of the display
    /// the pointer is on, anchored to nothing, so it cannot read as labelling the wrong control.
    private static func instructionFrame() -> NSRect {
        let pointer = NSEvent.mouseLocation
        let screen =
            NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen else { return NSRect(x: 0, y: 0, width: 460, height: 90) }
        let size = CGSize(width: 460, height: 92)
        let visible = screen.visibleFrame
        return NSRect(
            x: (visible.midX - size.width / 2).rounded(),
            y: (visible.maxY - size.height - 28).rounded(),
            width: size.width,
            height: size.height)
    }

    /// CoreGraphics and the Accessibility API both hand back a top-left origin measured from the
    /// primary display; `NSWindow` wants bottom-left. Getting this backwards puts the ring at the
    /// bottom of the screen, which is how `MenuBarSpotlight` learned to write it down.
    private static func flipped(_ rect: CGRect) -> NSRect {
        guard let primary = NSScreen.screens.first else { return rect }
        return NSRect(
            x: rect.origin.x,
            y: primary.frame.maxY - rect.origin.y - rect.height,
            width: rect.width,
            height: rect.height)
    }

    private static func present(frame: NSRect, guidance: PermissionGuidance, caption: String) {
        let host =
            window
            ?? {
                let w = NSWindow(
                    contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
                w.isOpaque = false
                w.backgroundColor = .clear
                w.hasShadow = false
                // Above System Settings, and never in the way of it: the user has to be able to
                // press the switch we are ringing.
                w.level = .floating
                w.ignoresMouseEvents = true
                w.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
                w.contentView = PermissionOverlayView(frame: NSRect(origin: .zero, size: frame.size))
                window = w
                return w
            }()

        host.setFrame(frame, display: true)
        host.contentView?.frame = NSRect(origin: .zero, size: frame.size)
        (host.contentView as? PermissionOverlayView)?.render(guidance, caption: caption)
        host.orderFrontRegardless()
    }
}

// MARK: - Overlay content

/// The ring, the hand and the caption — or, when there is nothing to point at, the caption alone.
///
/// Deliberately not a `NSHostingView`: this window is recreated and repositioned on a 400 ms tracker
/// while another application has focus, and a `CALayer` tree redraws under that without SwiftUI
/// re-running a view body each tick.
final class PermissionOverlayView: NSView {
    /// The strip below the ring that holds the hand. Owned here, and read by `PermissionOverlay`
    /// when it sizes the window, so the window can never be too short for what this draws in it.
    static let handRoom: CGFloat = 56

    private let ring = CAShapeLayer()
    private let hand = NSImageView()
    private let caption = NSTextField(labelWithString: "")
    private let plate = NSVisualEffectView()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true

        ring.fillColor = NSColor.clear.cgColor
        // The accent, for the same reason `MenuBarSpotlight`'s ring is: this lands on another
        // application's window, whose background is unknowable from here, so neither end of the
        // label ladder is guaranteed to show up on it.
        ring.strokeColor = Ink.nsAccent.withAlphaComponent(0.95).cgColor
        ring.lineWidth = 3
        layer?.addSublayer(ring)

        // An SF Symbol rather than a drawn hand or an emoji: it is the system's own pointing glyph,
        // it takes a tint, and it carries the accent the ring is already drawn in.
        hand.image = NSImage(
            systemSymbolName: "hand.point.up.left.fill",
            accessibilityDescription: "Points at the row to switch on")
        hand.symbolConfiguration = .init(pointSize: 26, weight: .medium)
        hand.contentTintColor = Ink.nsAccent
        hand.imageScaling = .scaleProportionallyUpOrDown
        hand.isHidden = true
        addSubview(hand)

        plate.material = .hudWindow
        plate.blendingMode = .withinWindow
        plate.state = .active
        plate.wantsLayer = true
        plate.layer?.cornerRadius = 11
        plate.layer?.cornerCurve = .continuous
        addSubview(plate)

        caption.font = .systemFont(ofSize: NSFont.systemFontSize)
        caption.textColor = .labelColor
        caption.alignment = .center
        caption.maximumNumberOfLines = 3
        caption.lineBreakMode = .byWordWrapping
        addSubview(caption)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not used") }

    /// What is currently drawn. The window is reused across relocations, so the view has to be able
    /// to go from ringing a row to saying a sentence without being rebuilt.
    private var guidance: PermissionGuidance?

    func render(_ guidance: PermissionGuidance, caption text: String) {
        self.guidance = guidance
        caption.stringValue = text

        switch guidance {
        case .pointing:
            ring.isHidden = false
            hand.isHidden = false
            plate.isHidden = true
            caption.isHidden = true
            beginPulse()
        case .instruction(let sentence):
            ring.isHidden = true
            ring.removeAllAnimations()
            hand.isHidden = true
            plate.isHidden = false
            caption.isHidden = false
            caption.stringValue = sentence
        }
        needsLayout = true
        layout()
    }

    /// Replaces the pointing hand with a checkmark and the pulse with a solid green ring. The instant
    /// TCC reports the grant, this is what the user sees before the overlay leaves.
    func showConfirmation(_ text: String) {
        ring.removeAllAnimations()
        ring.opacity = 1
        ring.strokeColor = NSColor.systemGreen.withAlphaComponent(0.95).cgColor
        hand.layer?.removeAllAnimations()
        hand.image = NSImage(
            systemSymbolName: "checkmark.circle.fill", accessibilityDescription: "Granted")
        hand.contentTintColor = .systemGreen
        hand.isHidden = false
        plate.isHidden = false
        caption.isHidden = false
        caption.stringValue = text
        isConfirming = true
        needsLayout = true
        layout()
    }

    /// Suppresses the hand's nudge once the grant has landed: a hand still tapping at a switch the
    /// user has already flipped is asking for something that is done.
    private var isConfirming = false

    override func layout() {
        super.layout()
        switch guidance {
        case .pointing:
            layoutRing()
        case .instruction, .none:
            layoutPlate()
        }
    }

    /// The ring hugs the row at the top of the window; the hand sits in the room left below it.
    private func layoutRing() {
        let handRoom = Self.handRoom
        // The view's coordinate system is bottom-left, and the row is at the *top* of the window.
        let rowBox = NSRect(
            x: ring.lineWidth,
            y: handRoom + ring.lineWidth,
            width: bounds.width - ring.lineWidth * 2,
            height: bounds.height - handRoom - ring.lineWidth * 2)
        ring.frame = bounds
        ring.path = CGPath(
            roundedRect: rowBox, cornerWidth: 9, cornerHeight: 9, transform: nil)

        // Under the row's trailing end, where the switch is — pointing up at the thing to press
        // rather than at the row in general.
        hand.frame = NSRect(x: bounds.width - 86, y: rowBox.minY - 40, width: 44, height: 34)
        // A grant confirmation puts the caption back on screen even in the pointing layout.
        if !caption.isHidden {
            plate.frame = NSRect(x: 0, y: 0, width: bounds.width, height: 30)
            caption.frame = plate.frame.insetBy(dx: 12, dy: 6)
        }
        beginHandNudge()
    }

    private func layoutPlate() {
        plate.frame = bounds
        caption.frame = bounds.insetBy(dx: 20, dy: 14)
    }

    // MARK: Motion

    /// Breathes, so the eye finds the ring on a pane full of near-identical rows. Static under
    /// Reduce Motion — the ring is still the answer, it just does not move.
    private func beginPulse() {
        ring.removeAllAnimations()
        guard !InkReduceMotion.isEnabled else {
            ring.opacity = 1
            return
        }
        let pulse = CABasicAnimation(keyPath: "opacity")
        pulse.fromValue = 1.0
        pulse.toValue = 0.4
        pulse.duration = 0.85
        pulse.autoreverses = true
        pulse.repeatCount = .infinity
        pulse.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        ring.add(pulse, forKey: "pulse")
    }

    private func beginHandNudge() {
        hand.layer?.removeAllAnimations()
        guard !isConfirming, !InkReduceMotion.isEnabled, let layer = hand.layer else { return }
        let nudge = CABasicAnimation(keyPath: "transform.translation.y")
        nudge.fromValue = 0
        nudge.toValue = 7
        nudge.duration = 0.6
        nudge.autoreverses = true
        nudge.repeatCount = .infinity
        nudge.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        layer.add(nudge, forKey: "nudge")
    }
}

// MARK: - Our own replica, on our own card

/// A ghost row rising into a list — ours, drawn by us, on our card, before the real pane opens.
///
/// This exists because the real affordance arrives cold otherwise: macOS 26 shows a dashed row and
/// an instruction to drag it up into the list, and a user meeting that for the first time in a
/// Privacy pane has to work out what it wants before they can do it. Half a second of *this* is what
/// makes the real one recognised on sight.
///
/// It is a rough likeness on purpose. Nothing here is a facsimile of System Settings' control and
/// nothing here is presented as System Settings — it sits on our sheet, in our palette, under a
/// caption that says what it is a preview of.
struct GhostRowReplica: View {
    /// How many settled rows sit above the one that rises. Three is enough to read as a list.
    private static let settledRows = 3
    private static let rowHeight: CGFloat = 22
    private static let riseSeconds: Double = 1.5

    @State private var risen = false
    @State private var switched = false
    /// Stops the loop when the card changes under it. Without this the replica keeps re-arming
    /// itself for the life of the process, long after the step that showed it.
    @State private var onScreen = false

    var body: some View {
        VStack(spacing: 5) {
            ForEach(0..<Self.settledRows, id: \.self) { index in
                row(ghost: false, on: index == 0, width: [0.52, 0.4, 0.46][index])
            }
            row(ghost: !risen, on: switched, width: 0.58)
                .offset(y: risen ? 0 : Self.rowHeight + 12)
                .opacity(risen ? 1 : 0.55)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(Ink.rowFill)
                .overlay(
                    RoundedRectangle(cornerRadius: 11, style: .continuous)
                        .strokeBorder(Ink.separator, lineWidth: 1))
        )
        .accessibilityLabel(Text("A preview of the row you are about to switch on in System Settings"))
        .onAppear {
            onScreen = true
            play()
        }
        .onDisappear { onScreen = false }
    }

    /// One row: a name bar and a switch. Dashed while it is still the ghost.
    private func row(ghost: Bool, on: Bool, width: CGFloat) -> some View {
        HStack(spacing: 8) {
            RoundedRectangle(cornerRadius: 3, style: .continuous)
                .fill(Ink.primary.opacity(ghost ? 0.16 : 0.3))
                .frame(height: 7)
                .frame(maxWidth: .infinity, alignment: .leading)
                .scaleEffect(x: width, anchor: .leading)
            switchShape(on: on)
        }
        .padding(.horizontal, 7)
        .frame(height: Self.rowHeight)
        .background(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(ghost ? Color.clear : Ink.primary.opacity(0.05))
                .overlay {
                    if ghost {
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(
                                Ink.hairline,
                                style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    }
                }
        )
    }

    /// A switch, in the accent when on — the user's own accent, which is the only accent this app
    /// ever draws with.
    private func switchShape(on: Bool) -> some View {
        Capsule(style: .continuous)
            .fill(on ? Ink.accent : Ink.primary.opacity(0.16))
            .frame(width: 22, height: 12)
            .overlay(alignment: on ? .trailing : .leading) {
                Circle()
                    .fill(Ink.surface)
                    .frame(width: 10, height: 10)
                    .padding(1)
            }
    }

    /// Rise, then flip. Under Reduce Motion it is simply already risen and already on: the still
    /// frame carries the same information, which is what the animation was for.
    private func play() {
        guard !InkReduceMotion.isEnabled else {
            risen = true
            switched = true
            return
        }
        // The reset is animated too. Snapping the row back to the bottom between passes reads as a
        // glitch, which is the one thing a preview cannot afford to look like.
        withAnimation(.easeIn(duration: 0.28)) {
            risen = false
            switched = false
        }
        withAnimation(.spring(response: 0.6, dampingFraction: 0.72).delay(0.5)) { risen = true }
        withAnimation(.easeOut(duration: 0.22).delay(1.3)) { switched = true }
        // Loops for as long as the card is up: the user is reading a sentence beside it, and one
        // pass finishing before they look is a preview they never saw.
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(Self.riseSeconds + 1.4))
            guard onScreen, !InkReduceMotion.isEnabled else { return }
            play()
        }
    }
}

#if DEBUG
#Preview("Ghost row") {
    GhostRowReplica()
        .frame(width: 320)
        .padding(40)
        .background(Ink.surface)
}
#endif
