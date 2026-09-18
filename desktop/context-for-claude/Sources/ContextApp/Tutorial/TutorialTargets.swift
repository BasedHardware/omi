import AppKit

/// Where the things a coach mark points at actually are.
///
/// Every answer here is discovered at runtime — from the window server, from `NSApp.windows`, from
/// our own view tree, or from our own accessibility tree — and every one of them can answer `nil`.
/// That matters more than the discovery: a coach mark with no target degrades to a plain card, and a
/// confident arrow aimed at where a window used to be is worse than a sentence. There is no fallback
/// rectangle anywhere in this file.
@MainActor
enum TutorialTargetLocator {

    /// AppKit screen coordinates (origin bottom-left of the primary display), which is what
    /// `NSWindow.setFrame` wants.
    static func frame(of target: TutorialTarget) -> CGRect? {
        switch target {
        case .timelineWindow: return timelineWindow()?.frame
        case .timelineTrack: return trackFrame()
        case .searchAllButton: return searchAllFrame()
        // Asked of the window that owns it rather than hunted for in `NSApp.windows`: the search
        // panel is borderless and titleless, so there is nothing to identify it by from outside, and
        // `SearchBarWindow` already holds the one reference to it. Nil while it is closed, which is
        // the ordinary state and which the caller has to live with.
        case .searchPanel: return SearchBarWindow.panelFrame
        }
    }

    // MARK: - Our own windows

    /// The timeline window, identified by the title `RewindWindow` set on it. Read from
    /// `NSApp.windows` rather than held as a reference because this file does not own that window and
    /// must not keep it alive.
    private static func timelineWindow() -> NSWindow? {
        NSApp.windows.first { $0.isVisible && $0.title == RewindView.modeTitle }
    }

    /// The track, from the real `RewindTrackView` in the real hierarchy.
    ///
    /// The track is drawn in AppKit, so it is a genuine `NSView` with a genuine frame — no layout
    /// constant is copied here, and if the window is resized or the track moves, this moves with it.
    private static func trackFrame() -> CGRect? {
        guard let window = timelineWindow(), let root = window.contentView,
              let track = firstSubview(of: root, ofType: RewindTrackView.self)
        else { return nil }
        return window.convertToScreen(track.convert(track.bounds, to: nil))
    }

    private static func firstSubview<T: NSView>(of view: NSView, ofType type: T.Type) -> T? {
        if let match = view as? T { return match }
        for subview in view.subviews {
            if let match = firstSubview(of: subview, ofType: type) { return match }
        }
        return nil
    }

    // MARK: - Our own SwiftUI controls

    /// The "Search All" pill.
    ///
    /// SwiftUI draws it into one hosting view, so there is no `NSView` to find — but there *is* an
    /// accessibility element, and its `accessibilityFrame()` is in screen coordinates. Walking our own
    /// tree in our own process needs no Accessibility grant: these are ordinary method calls on our
    /// own objects, not the AX client API.
    ///
    /// SwiftUI builds that tree lazily, so this genuinely can answer nil, and the caller must be able
    /// to live with a card instead of an arrow.
    private static func searchAllFrame() -> CGRect? {
        guard let window = timelineWindow(), let root = window.contentView else {
            searchAllCache = nil
            return nil
        }
        if let found = accessibleFrame(under: root, matching: searchAllTitle) { return found }
        // The in-process tree did not answer. Ask the way an assistive client would, off the main
        // thread, and use whatever the last probe found.
        refreshSearchAllFromAccessibilityServer()
        return searchAllCache
    }

    /// The pill's own accessibility title, as SwiftUI exposes it.
    private static let searchAllTitle = "Search All"

    /// Last frame the out-of-band probe found, in AppKit screen coordinates. Nil until one succeeds,
    /// which is why the coach mark has to be able to live without it.
    nonisolated(unsafe) private static var searchAllCache: CGRect?
    nonisolated(unsafe) private static var searchAllProbeIsRunning = false
    private static var searchAllProbedAt: Double = 0

    /// Asks the accessibility server for our own tree, on a background queue.
    ///
    /// SwiftUI builds that tree lazily and only for a real client request, which is why walking our
    /// own views in-process can come back empty while an external dump of the same window shows the
    /// button plainly. Asking the server is how the tree comes into being.
    ///
    /// **Never on the main thread.** An `AXUIElement` request against our own process is serviced *by*
    /// our main thread, so a synchronous call from there deadlocks the app. This starts the work, keeps
    /// at most one in flight, and returns immediately; the coach mark uses the previous answer and
    /// points at nothing until there is one.
    private static func refreshSearchAllFromAccessibilityServer() {
        let now = ProcessInfo.processInfo.systemUptime
        guard !searchAllProbeIsRunning, now - searchAllProbedAt > 1.5 else { return }
        searchAllProbeIsRunning = true
        searchAllProbedAt = now
        let pid = ProcessInfo.processInfo.processIdentifier
        let needle = searchAllTitle
        DispatchQueue.global(qos: .userInitiated).async {
            let found = SelfAccessibility.frameOfButton(matching: needle, in: pid)
            searchAllCache = found
            searchAllProbeIsRunning = false
        }
    }

    /// Depth- and breadth-bounded: this runs on a poll tick, and an unbounded walk of a SwiftUI tree
    /// on a timer is a way to make a window feel broken.
    private static let maximumDepth = 16
    private static let maximumVisited = 3_000

    /// Walks views *and* accessibility elements together.
    ///
    /// Both halves are needed, and the first version of this only had one. `NSView`'s default
    /// `accessibilityChildren()` is nil — the AX server builds a view's children itself — so a walk
    /// that only followed accessibility children stopped dead at the window's content view and every
    /// coach mark degraded to a centred card. Descending `subviews` reaches the `NSHostingView`, which
    /// *does* answer `accessibilityChildren()` with SwiftUI's own elements, and those carry the frames.
    private static func accessibleFrame(under root: Any, matching needle: String) -> CGRect? {
        var visited = 0
        var queue: [(node: Any, depth: Int)] = [(root, 0)]

        while !queue.isEmpty {
            let (node, depth) = queue.removeFirst()
            visited += 1
            if visited > maximumVisited || depth > maximumDepth { return nil }

            if let accessible = node as? NSAccessibilityProtocol {
                let title = [
                    accessible.accessibilityTitle(),
                    accessible.accessibilityLabel(),
                    accessible.accessibilityHelp(),
                ].compactMap { $0 }.joined(separator: " ")
                if title.localizedCaseInsensitiveContains(needle),
                   let element = node as? NSAccessibilityElementProtocol {
                    let frame = element.accessibilityFrame()
                    // A zero-sized element is a node that exists but has not been laid out; pointing
                    // at the origin of the primary display would be the exact failure this guards.
                    if frame.width > 1, frame.height > 1 { return frame }
                }
                for child in accessible.accessibilityChildren() ?? [] {
                    queue.append((child, depth + 1))
                }
            }
            if let view = node as? NSView {
                for subview in view.subviews { queue.append((subview, depth + 1)) }
            }
        }
        return nil
    }

}

// MARK: - Our own accessibility tree, asked for the way a client asks

/// Reads *this* process's accessibility tree through the accessibility server.
///
/// Only for SwiftUI content, and only from a background queue. Everything drawn in AppKit is reachable
/// through the view hierarchy, which is cheaper and synchronous — this exists because SwiftUI's tree
/// is built on demand for a client request, so a coach mark that has to point at a SwiftUI control has
/// no other way to learn where it is.
///
/// Deliberately bounded: a fixed depth, a fixed node budget, and no attribute read other than role,
/// title, description and frame.
enum SelfAccessibility {
    private static let maximumDepth = 18
    private static let maximumVisited = 4_000

    /// The frame of the first button whose title or description contains `needle`, in AppKit screen
    /// coordinates, or nil.
    static func frameOfButton(matching needle: String, in pid: pid_t) -> CGRect? {
        let application = AXUIElementCreateApplication(pid)
        guard let windows = copy(application, kAXWindowsAttribute) as? [AXUIElement] else { return nil }
        var visited = 0
        for window in windows {
            if let found = search(window, needle: needle, depth: 0, visited: &visited) {
                return flipped(found)
            }
        }
        return nil
    }

    /// Accessibility hands back a top-left origin measured from the primary display; `NSWindow` wants
    /// bottom-left. Computed here rather than on the main actor because this runs on a background
    /// queue, and `NSScreen.screens` is safe to read for geometry.
    private static func flipped(_ rect: CGRect) -> CGRect? {
        guard let primary = NSScreen.screens.first else { return nil }
        return CGRect(
            x: rect.origin.x,
            y: primary.frame.maxY - rect.origin.y - rect.height,
            width: rect.width,
            height: rect.height)
    }

    private static func search(
        _ element: AXUIElement, needle: String, depth: Int, visited: inout Int
    ) -> CGRect? {
        visited += 1
        if depth > maximumDepth || visited > maximumVisited { return nil }

        let role = copy(element, kAXRoleAttribute) as? String
        if role == (kAXButtonRole as String) {
            let title = [
                copy(element, kAXTitleAttribute) as? String,
                copy(element, kAXDescriptionAttribute) as? String,
            ].compactMap { $0 }.joined(separator: " ")
            if title.localizedCaseInsensitiveContains(needle), let frame = frame(of: element),
                frame.width > 1, frame.height > 1
            {
                return frame
            }
        }
        for child in copy(element, kAXChildrenAttribute) as? [AXUIElement] ?? [] {
            if let found = search(child, needle: needle, depth: depth + 1, visited: &visited) {
                return found
            }
        }
        return nil
    }

    private static func copy(_ element: AXUIElement, _ attribute: String) -> CFTypeRef? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success else {
            return nil
        }
        return value
    }

    private static func frame(of element: AXUIElement) -> CGRect? {
        guard let positionValue = copy(element, kAXPositionAttribute),
            let sizeValue = copy(element, kAXSizeAttribute),
            CFGetTypeID(positionValue) == AXValueGetTypeID(),
            CFGetTypeID(sizeValue) == AXValueGetTypeID()
        else { return nil }
        var origin = CGPoint.zero
        var size = CGSize.zero
        guard AXValueGetValue(positionValue as! AXValue, .cgPoint, &origin),
            AXValueGetValue(sizeValue as! AXValue, .cgSize, &size)
        else { return nil }
        return CGRect(origin: origin, size: size)
    }
}
