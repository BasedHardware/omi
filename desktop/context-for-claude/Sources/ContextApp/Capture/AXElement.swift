import ApplicationServices
import ContextCore
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
    }

    /// The focused window of a process, or nil when there is nothing to read.
    ///
    /// Returns nil rather than falling back to the application element or its first window: a tree
    /// captured from a window the user was not looking at is worse than no tree at all, because
    /// nothing downstream can tell it apart from one they were.
    static func focusedWindow(pid: pid_t) -> AXElement? {
        let app = AXUIElementCreateApplication(pid)
        guard let window = copy(kAXFocusedWindowAttribute, from: app),
              CFGetTypeID(window) == AXUIElementGetTypeID()
        else { return nil }
        return AXElement(window as! AXUIElement)
    }

    /// Whether this process may read other applications' interfaces at all.
    ///
    /// Never prompts. Accessibility is not a permission that can be requested from code the way the
    /// microphone can — the system offers no dialog that grants it — so asking is a separate,
    /// deliberate act and this stays a pure question.
    static var isTrusted: Bool { AXIsProcessTrusted() }

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
