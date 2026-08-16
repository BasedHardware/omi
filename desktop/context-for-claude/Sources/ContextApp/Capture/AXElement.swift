import ApplicationServices
import ContextCore
import CoreGraphics
import Foundation

/// A live `AXUIElement`, seen through the narrow protocol the tree walker actually needs.
///
/// Every property here is one synchronous inter-process message to another application, which is the
/// entire reason the walker is bounded by a wall clock: an app that is beachballing answers these
/// slowly, or not at all, and there is no ceiling on how many children it can claim to have.
///
/// This type makes no policy decisions — no limits, no redaction, no judgement about what is worth
/// keeping. It only answers questions, so the code that does decide those things stays testable
/// without a GUI.
struct AXElement: AXElementSource {
    private let element: AXUIElement

    init(_ element: AXUIElement) {
        self.element = element
        // Set on every element this type wraps, and that repetition is the API's, not a choice:
        // `AXUIElementSetMessagingTimeout` is documented to apply to the object it is called on and
        // not to objects equal to it, so a timeout on the application element would leave every
        // child read — which is all of them — on the six-second default.
        AXUIElementSetMessagingTimeout(element, Self.messagingTimeout)
    }

    /// Ceiling on a single accessibility message, in seconds.
    ///
    /// Without one, every read here waits on the system default of **six seconds**. The walker's
    /// wall-clock budget (``AXCaptureLimits/budget``) is checked *between* elements and cannot
    /// interrupt a call already in flight, so it bounded nothing: a beachballing renderer stalled a
    /// capture tick for six seconds, twice — once for the address probe and once for the tree — on
    /// the cooperative pool the rest of the app shares. The comment promising that such an app
    /// "must cost a missing URL rather than a stalled pipeline" was, until this line, false.
    ///
    /// A quarter second is the same order as the budget it is protecting (0.25 s for a tree, 0.1 s
    /// for the address probe) and roughly two hundred times a healthy read. The two ceilings
    /// compose: one slow element costs at most its own attribute reads at this timeout, and the
    /// budget check between elements then ends the walk — so the worst case is seconds' worth of
    /// stall turned into a fraction of one, and an unresponsive application costs a shallower tree
    /// rather than a wedged tick.
    ///
    /// Set here rather than on the system-wide element on purpose. The system-wide object would
    /// impose this process-wide, and other parts of the app drive accessibility for very different
    /// work — `PermissionChoreography` sets its own 0.35 s on System Settings — where a quarter
    /// second is not the right answer.
    static let messagingTimeout: Float = 0.25

    /// How many of an application's windows are examined before the search gives up.
    ///
    /// An application can claim any number of windows and each candidate costs messages, so this is
    /// bounded like every other axis of a walk. Well above what any real application has open.
    static let maxWindowsInspected = 32

    /// The element that may be read as the window `captured` describes, or nil.
    ///
    /// Nil rather than a best guess: a tree or an address read from a window other than the one
    /// whose pixels were taken is not weaker evidence about that frame, it is evidence about a
    /// different frame, and nothing downstream can tell the two apart. ``AXWindowMatch`` holds the
    /// rule; the order here is about cost and about what macOS is actually willing to answer.
    ///
    /// 1. **The focused element.** One message, where enumerating costs one plus two per window,
    ///    and it is the captured window on nearly every tick. Checked rather than assumed — except
    ///    when the window server listed only one window, where there is nothing to check it
    ///    against.
    /// 2. **The application's windows**, filtered to things that really are windows. `AXWindows` is
    ///    not promised to contain windows and demonstrably does not: measured live on this machine,
    ///    Warp answered its own application element and Finder answered a scroll area, and walking
    ///    either spends the whole budget on a menu bar.
    ///
    /// What it will not do is fall back to "the focused element anyway" when an application has more
    /// than one window: that is precisely the case this exists to refuse.
    static func window(pid: pid_t, matching captured: CapturedWindow) -> AXElement? {
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, messagingTimeout)

        if let focused = elementValue(kAXFocusedWindowAttribute, from: app),
            AXWindowMatch.isCapturedWindow(focused, matching: captured)
        {
            return focused
        }

        guard let raw = copy(kAXWindowsAttribute, from: app),
            CFGetTypeID(raw) == CFArrayGetTypeID(),
            let array = raw as? [AnyObject]
        else { return nil }
        let windows = array.prefix(maxWindowsInspected).compactMap { window -> AXElement? in
            guard CFGetTypeID(window) == AXUIElementGetTypeID() else { return nil }
            let element = AXElement(window as! AXUIElement)
            return element.axRole == kAXWindowRole ? element : nil
        }
        if let matched = AXWindowMatch.window(matching: captured, in: windows) { return matched }
        // One window listed by the window server and one real window here: the same "nothing else it
        // could be" as above, reached when the application would not answer which one has focus.
        return captured.wasOnlyWindow && windows.count == 1 ? windows[0] : nil
    }

    /// An attribute whose value is itself an accessibility element, wrapped so that it carries
    /// the messaging timeout like every other element this type hands out.
    private static func elementValue(_ attribute: String, from element: AXUIElement) -> AXElement? {
        guard let value = copy(attribute, from: element),
              CFGetTypeID(value) == AXUIElementGetTypeID()
        else { return nil }
        return AXElement(value as! AXUIElement)
    }

    /// Whether this process may read other applications' interfaces at all.
    ///
    /// Never prompts. Accessibility is not a permission that can be requested from code the way the
    /// microphone can — the system offers no dialog that grants it — so asking is a separate,
    /// deliberate act and this stays a pure question. `requestTrust()` below is that act.
    static var isTrusted: Bool { AXIsProcessTrusted() }

    /// The same question, asked out loud.
    ///
    /// **This is not a grant dialog and the distinction matters.** No API grants Accessibility;
    /// the switch is flipped by hand in Privacy & Security. What `kAXTrustedCheckOptionPrompt`
    /// buys is the two things opening the pane cannot: macOS shows the standard "would like to
    /// control this computer" alert with a button that leads straight there, and — the part that
    /// actually unblocks people — it **registers this app in that list**. An app that has never
    /// asked is not listed at all, so a user sent to the pane finds no row to switch on and has to
    /// know about the `+` button and go hunting for the bundle. That is the state
    /// `⌘ + ⌘` shipped in: a gesture that cannot fire, pointing at a pane that cannot fix it.
    ///
    /// - Returns: whether trust is held *now*. The dialog is asynchronous and the user has to leave
    ///   for System Settings, so this is almost always `false` on the call that raises it; the real
    ///   answer arrives on the next `refresh()`, which app activation already triggers.
    @discardableResult
    static func requestTrust() -> Bool {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue()
        return AXIsProcessTrustedWithOptions([key: true] as CFDictionary)
    }

    var axRole: String? { string(kAXRoleAttribute) }
    var axSubrole: String? { string(kAXSubroleAttribute) }
    var axTitle: String? { string(kAXTitleAttribute) }
    var axDescription: String? { string(kAXDescriptionAttribute) }

    /// Only a string value is read.
    ///
    /// `AXValue` is typed: sliders answer with numbers, scroll areas with rectangles, a table with
    /// its selection. None of that is text a person read, and storing it would fill the index with
    /// coordinates.
    var axValue: String? { string(kAXValueAttribute) }

    /// The address of the document this element is showing.
    ///
    /// Two attributes because the two browser engines put it in different places, and neither is a
    /// fallback for the other:
    ///
    /// - `AXURL` is a `CFURLRef` and is what WebKit and Chromium answer on an `AXWebArea` — the
    ///   element that *is* the page. It is also what a document window answers when the application
    ///   set `NSWindow.representedURL`.
    /// - `AXDocument` is a `CFStringRef` holding the same thing, and is what Safari puts on the
    ///   window itself.
    ///
    /// The type is checked before either is read for the same reason as ``axValue``: `as? String`
    /// alone would accept anything CoreFoundation is willing to bridge, and a value that is not an
    /// address must read as *no* address rather than as a nonsense one — the gate treats a URL it
    /// was given as authoritative.
    ///
    /// This needs no permission beyond the Accessibility grant the walker already requires: it is
    /// the same `AXUIElementCopyAttributeValue` call, on the same element, as every other attribute
    /// on this type.
    var axURL: String? {
        if let value = Self.copy(kAXURLAttribute, from: element) {
            if CFGetTypeID(value) == CFURLGetTypeID(), let url = value as? URL {
                return url.absoluteString
            }
            if CFGetTypeID(value) == CFStringGetTypeID() { return value as? String }
        }
        return string(kAXDocumentAttribute)
    }

    /// The window's rectangle, in points, from the two attributes that carry it.
    ///
    /// Both or neither: a position without a size is not a place, and half an answer here would be
    /// compared against a whole one. `AXValue` is a typed box, so the type is checked before it is
    /// unpacked for the same reason as everywhere else on this type — a value that is not a point
    /// must read as no point rather than as the origin.
    var axFrame: CGRect? {
        guard let origin = point(kAXPositionAttribute),
              let size = self.size(kAXSizeAttribute)
        else { return nil }
        return CGRect(origin: origin, size: size)
    }

    var axChildren: [any AXElementSource] {
        guard let raw = Self.copy(kAXChildrenAttribute, from: element),
              CFGetTypeID(raw) == CFArrayGetTypeID(),
              let array = raw as? [AnyObject]
        else { return [] }
        return array.compactMap { child in
            guard CFGetTypeID(child) == AXUIElementGetTypeID() else { return nil }
            return AXElement(child as! AXUIElement)
        }
    }

    // MARK: - Attribute reads

    private func point(_ attribute: String) -> CGPoint? {
        var point = CGPoint.zero
        guard let value = boxedValue(attribute, of: .cgPoint),
              AXValueGetValue(value, .cgPoint, &point)
        else { return nil }
        return point
    }

    private func size(_ attribute: String) -> CGSize? {
        var size = CGSize.zero
        guard let value = boxedValue(attribute, of: .cgSize),
              AXValueGetValue(value, .cgSize, &size)
        else { return nil }
        return size
    }

    private func boxedValue(_ attribute: String, of type: AXValueType) -> AXValue? {
        guard let value = Self.copy(attribute, from: element),
              CFGetTypeID(value) == AXValueGetTypeID()
        else { return nil }
        let boxed = value as! AXValue
        guard AXValueGetType(boxed) == type else { return nil }
        return boxed
    }

    private func string(_ attribute: String) -> String? {
        guard let value = Self.copy(attribute, from: element),
              // The type check is what keeps a slider's position out of the text index: `as? String`
              // alone would accept anything CoreFoundation is willing to bridge.
              CFGetTypeID(value) == CFStringGetTypeID()
        else { return nil }
        return value as? String
    }

    private static func copy(_ attribute: String, from element: AXUIElement) -> AnyObject? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
        // Any error means "this element does not answer that", which is ordinary rather than
        // exceptional: not every element has a title, and an application that just quit answers
        // nothing at all. Logging it would produce a line per element per tick.
        guard result == .success else { return nil }
        return value
    }
}
