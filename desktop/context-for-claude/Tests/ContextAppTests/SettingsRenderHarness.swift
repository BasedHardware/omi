import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the **real** `SettingsView` — every pane, at the window's real size — and writes the
/// frames out for a person to look at.
///
/// **Skipped unless `CONTEXT_SETTINGS_RENDER=1`.** It writes files and exists to be run by hand; the
/// claims that must hold every time are in `SettingsTests`, which is pure and hermetic.
///
/// It exists because the panes are the one part of this package whose defects are *visual* — a
/// section left behind, a row in the wrong place, a window the wrong size — and the alternative way
/// to look at them is to install a build over the user's running app, which shares its bundle
/// identifier, its support directory and its TCC records. `ImageRenderer` over the shipping view
/// costs none of that and shows the same pixels.
///
/// Nothing of the user's reaches a frame: the store is built on a throwaway `UserDefaults` suite with
/// `appliesToRunningApp: false`, the exclusions engine on a temporary directory, and the shortcut
/// provider is the in-memory stand-in that registers nothing.
final class SettingsRenderHarness: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("settings-render-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    @MainActor
    func testRenderEveryPane() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_SETTINGS_RENDER"] == "1",
            "render harness; set CONTEXT_SETTINGS_RENDER=1 to run it")

        let directory = URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_SETTINGS_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "settings-renders")
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let suite = "context.settings.render.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        let store = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        let engine = ExclusionEngine(
            configurationURL: root.appendingPathComponent("exclusions.json"),
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
        let observer = ExclusionsObserver(engine: engine)

        for pane in SettingsPane.allCases {
            let view = SettingsView(
                store: store,
                exclusions: observer,
                shortcuts: InMemoryShortcutBindings(chords: [:]),
                selection: SettingsSelection(pane: pane))

            let image = try XCTUnwrap(render(view), "\(pane.title) did not render")
            try write(image, to: directory, named: pane.rawValue)
        }

        print("[settings] rendered \(SettingsPane.allCases.count) panes to \(directory.path)")
        print(
            "[settings] window \(Int(SettingsMetrics.windowSize.width))×"
                + "\(Int(SettingsMetrics.windowSize.height)), the timeline's own size")
    }

    /// Hosted in a real (offscreen) window and cached, rather than run through `ImageRenderer`.
    ///
    /// `ImageRenderer` was tried first and draws the sidebar and the header and then **nothing**:
    /// every pane sits inside `SettingsPaneScroll`, and a `ScrollView` has no content to hand a
    /// renderer that is not a window. An `NSHostingView` in an ordered-out `NSWindow` is the same
    /// code path the app itself uses, which is also the only thing that makes these frames worth
    /// looking at.
    @MainActor
    private func render(_ view: SettingsView) -> NSImage? {
        let size = SettingsMetrics.windowSize
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered,
            defer: false)
        // The window normally paints `InkGlassView` behind this; without a ground, `cacheDisplay`
        // composites dark text against transparency and the frame comes out as a ghost. `Ink.surface`
        // is the same colour the glass resolves to.
        let hosting = NSHostingView(
            rootView: ZStack { Ink.surface.ignoresSafeArea(); view })
        hosting.frame = NSRect(origin: .zero, size: size)
        window.contentView = hosting
        window.orderBack(nil)
        hosting.layoutSubtreeIfNeeded()
        // One turn of the run loop, so SwiftUI has actually drawn into the layer.
        RunLoop.current.run(until: Date().addingTimeInterval(0.15))

        guard let rep = hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds) else { return nil }
        hosting.cacheDisplay(in: hosting.bounds, to: rep)
        window.orderOut(nil)

        let image = NSImage(size: hosting.bounds.size)
        image.addRepresentation(rep)
        return image
    }

    /// **Fails rather than skips.** This threw `XCTSkip` on an encoding failure, which is exactly
    /// the outcome the harness exists to catch: a pane whose draw path regressed would report
    /// "skipped" while the summary below went on claiming every pane had rendered. The only skip in
    /// this file is the opt-in gate at the top.
    private func write(_ image: NSImage, to directory: URL, named name: String) throws {
        let png = try XCTUnwrap(
            image.tiffRepresentation
                .flatMap(NSBitmapImageRep.init(data:))
                .flatMap { $0.representation(using: .png, properties: [:]) },
            "\(name) produced an image that could not be encoded — the pane did not draw")
        try png.write(to: directory.appendingPathComponent("\(name).png"))
    }
}
