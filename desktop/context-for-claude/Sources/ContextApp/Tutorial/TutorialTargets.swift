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
        case .browserWindow: return browserWindowFrame()
        case .timelineWindow: return timelineWindow()?.frame
        case .timelineTrack: return trackFrame()
        case .searchAllButton: return searchAllFrame()
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
        guard let window = timelineWindow(), let root = window.contentView else { return nil }
        return accessibleFrame(under: root, matching: "Search All")
    }

    /// Depth- and breadth-bounded: this runs on a poll tick, and an unbounded walk of a SwiftUI tree
    /// on a timer is a way to make a window feel broken.
    private static let maximumDepth = 16
    private static let maximumVisited = 3_000

    private static func accessibleFrame(under root: Any, matching needle: String) -> CGRect? {
        var visited = 0
        var queue: [(node: Any, depth: Int)] = [(root, 0)]

        while !queue.isEmpty {
            let (node, depth) = queue.removeFirst()
            visited += 1
            if visited > maximumVisited || depth > maximumDepth { return nil }

            if let accessible = node as? NSAccessibilityProtocol {
                let title = accessible.accessibilityTitle() ?? accessible.accessibilityLabel() ?? ""
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
        }
        return nil
    }

    // MARK: - The browser

    /// The default browser's frontmost window.
    ///
    /// The browser is found by asking Launch Services which application opens an `https` URL, not by
    /// guessing at Safari: the tutorial opened the article in the *default* browser, so that is the
    /// window the coach mark has to sit beside.
    ///
    /// Bounds come from `CGWindowListCopyWindowInfo`, which needs no permission for geometry (unlike
    /// window *titles*, which this deliberately never reads).
    private static func browserWindowFrame() -> CGRect? {
        guard let probe = URL(string: "https://en.wikipedia.org"),
              let application = NSWorkspace.shared.urlForApplication(toOpen: probe),
              let bundleIdentifier = Bundle(url: application)?.bundleIdentifier
        else { return nil }

        let running = NSRunningApplication.runningApplications(withBundleIdentifier: bundleIdentifier)
        guard !running.isEmpty else { return nil }
        let pids = Set(running.map(\.processIdentifier))

        guard let listing = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        else { return nil }

        var best: CGRect?
        for entry in listing {
            guard let owner = entry[kCGWindowOwnerPID as String] as? pid_t, pids.contains(owner),
                  (entry[kCGWindowLayer as String] as? Int) == 0,
                  let bounds = entry[kCGWindowBounds as String] as? [String: Any],
                  let rect = CGRect(dictionaryRepresentation: bounds as CFDictionary)
            else { continue }
            // The largest layer-0 window: a browser also owns tiny helper windows, and the frontmost
            // one in list order is not reliably the document window.
            if best == nil || rect.width * rect.height > best!.width * best!.height { best = rect }
        }
        guard let found = best, found.width > 80, found.height > 80 else { return nil }
        return flippedFromCoreGraphics(found)
    }

    /// CoreGraphics hands back a top-left origin measured from the primary display; `NSWindow` wants
    /// bottom-left. Getting this backwards puts the coach mark at the bottom of the screen — the same
    /// bug `MenuBarSpotlight` documents.
    static func flippedFromCoreGraphics(_ rect: CGRect) -> CGRect? {
        guard let primary = NSScreen.screens.first else { return nil }
        return CGRect(
            x: rect.origin.x,
            y: primary.frame.maxY - rect.origin.y - rect.height,
            width: rect.width,
            height: rect.height)
    }
}
