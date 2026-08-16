import AppKit
import CoreImage
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the search surface as it really composites — live views, in a real window, over a
/// synthetic desktop — and writes the frames out for a person to look at.
///
/// **Skipped unless `CONTEXT_SEARCH_RENDER=1`.** It puts windows on screen and shells out to
/// `screencapture`, neither of which belongs in a hermetic suite; it is a tool for looking at the
/// thing, run by hand, and the assertions that have to hold every time live in
/// `SearchSurfaceTests`.
///
/// Two rules it exists to obey:
///
/// - **Live views and a run loop, never `ImageRenderer`.** The panels are `.behindWindow` glass and
///   an `ImageRenderer` pass has no window to be behind — it renders the scrim over nothing and
///   restarts every animation clock it touches. The only way to see what ships is to put it on a
///   screen.
/// - **Nothing of the user's is ever captured.** A full-screen opaque backdrop window covers the
///   exact rectangle that gets captured, so the frame contains this harness's own windows and the
///   synthetic desktop under them and nothing else. The data is fabricated in `Fixtures` below.
final class SearchRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_SEARCH_RENDER_DIR"]
            ?? NSTemporaryDirectory() + "search-renders")
    }

    @MainActor
    func testRenderTheSearchSurface() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_SEARCH_RENDER"] == "1",
            "on-screen render harness; set CONTEXT_SEARCH_RENDER=1 to run it")
        _ = InkTestFonts.registered

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let thumbnails = try Fixtures.thumbnails(in: directory)

        NSApplication.shared.setActivationPolicy(.accessory)

        // state × desktop × system appearance. The panel is pinned light in all of them; the Dark
        // pass is what proves the pin rather than assuming it.
        //
        // The first three are the states the two shipped defects lived in, and they are first on
        // purpose: an untouched bar over an empty capture and an untouched bar over a full one are
        // both states nobody had looked at, and both used to be reported as a failed search.
        let cases: [(name: String, query: String, model: SearchResultsModel)] = [
            ("00-untouched-fresh-install", "", Fixtures.freshInstall()),
            ("01-untouched-populated", "", Fixtures.twelve(thumbnails: thumbnails)),
            ("02-typed-none", "zzzz nothing matches", Fixtures.none()),
            ("03-typed-twelve", "gpu benchmarks", Fixtures.twelve(thumbnails: thumbnails)),
            ("04-typed-hundred", "screenshot", Fixtures.hundred(thumbnails: thumbnails)),
            ("05-typed-three", "invoice", Fixtures.few(3, thumbnails: thumbnails)),
            ("06-typed-one", "invoice", Fixtures.one(thumbnails: thumbnails)),
            ("07-missing-thumbnails", "retention", Fixtures.missingPictures()),
            // Both halves of the capture on one page, which is the state the merge exists for: a
            // conversation card and a screen card have to be legible as different things without a
            // badge, and identical in size so the grid rows stay level.
            ("10-typed-mixed", "invoice", Fixtures.mixed(thumbnails: thumbnails)),
            // The filter block **open**, which is now a state you have to ask for. It is here
            // because it is the state the panel's ceiling is hardest on — the three sections plus a
            // whole card — and because it is the only render that shows the chips at all now that
            // the panel opens on the grid.
            ("11-typed-twelve-filters-open", "gpu benchmarks", Fixtures.filtersOpen(thumbnails: thumbnails)),
            // …and the other half of that bargain: a narrowing the closed block is not showing has
            // to be named in the header, or a count that fell from 109 to 4 has no visible cause.
            ("12-narrowed-filters-closed", "gpu benchmarks", Fixtures.narrowedButClosed(thumbnails: thumbnails)),
        ]

        var written: [String] = []
        for (name, query, model) in cases {
            // The panel's copy follows the bar, in the harness exactly as in the app: the model is
            // told what was typed rather than inferring it from the fact that it has rows.
            model.ask(query)
            let path = try render(
                name: "\(name)-lightsystem-midgrey", query: query, model: model,
                desktop: Fixtures.desktopImage(.midGrey), appearance: .aqua, in: directory)
            written.append(path)
        }
        // The far end of the same scroll. The bottom edge's fade has to point at content that is
        // really there, so the state to look at is the one where it is not: scrolled to the end, the
        // last row's title and source line must be untouched, with the fade falling on the spare
        // room under them instead.
        let scrolled = Fixtures.hundred(thumbnails: thumbnails)
        scrolled.ask("screenshot")
        written.append(
            try render(
                name: "09-typed-hundred-scrolled-to-end-lightsystem-midgrey",
                query: "screenshot", model: scrolled,
                desktop: Fixtures.desktopImage(.midGrey), appearance: .aqua,
                scrollToEnd: true, in: directory))
        // The two extremes, on the state with the most type on it, in both system appearances —
        // this is the pair the contrast table is measured against.
        for (appearance, desktop) in [
            (NSAppearance.Name.aqua, Fixtures.Desktop.black),
            (NSAppearance.Name.aqua, Fixtures.Desktop.white),
            (NSAppearance.Name.darkAqua, Fixtures.Desktop.black),
            (NSAppearance.Name.darkAqua, Fixtures.Desktop.white),
        ] {
            let model = Fixtures.twelve(thumbnails: thumbnails)
            model.ask("gpu benchmarks")
            let path = try render(
                name: "08-typed-twelve-\(appearance == .aqua ? "lightsystem" : "darksystem")-\(desktop)",
                query: "gpu benchmarks",
                model: model,
                desktop: Fixtures.desktopImage(desktop),
                appearance: appearance,
                in: directory)
            written.append(path)
        }

        print("\n=== search surface renders ===")
        for path in written { print(path) }
        print("==============================\n")
    }

    // MARK: - Rendering

    /// Puts the surface on screen over a synthetic desktop and captures the desktop's rectangle.
    @MainActor
    private func render(
        name: String,
        query: String,
        model: SearchResultsModel,
        desktop: NSImage,
        appearance: NSAppearance.Name,
        scrollToEnd: Bool = false,
        in directory: URL
    ) throws -> String {
        NSApp.appearance = NSAppearance(named: appearance)

        let screen = try XCTUnwrap(NSScreen.main)
        let surface = SearchLayout.surfaceWidth
        // The tallest the surface can get. The shipped window resizes itself to the measured height
        // (`onHeightChange`); this harness has no such loop, so it opens at the ceiling and lets the
        // panel sit shorter inside it rather than clipping a panel that grew.
        let height = SearchLayout.surfaceHeight(
            showingNote: false,
            panelHeight: SearchLayout.panelHeaderHeight + SearchLayout.maximumResultsBodyHeight)
        // The captured rectangle: the surface plus a frame of synthetic desktop around it, so the
        // shadow and the glass have something real to sit on and the whole capture is ours.
        let inset: CGFloat = 34
        // Clamped into the screen's visible frame: `screencapture -R` refuses a rectangle that runs
        // off the display, and the surface at its ceiling is taller than the naive centring allows.
        let visible = screen.visibleFrame
        let wanted = NSSize(
            width: min(surface + inset * 2, visible.width),
            height: min(height + inset * 2, visible.height))
        let backdropFrame = NSRect(
            x: (visible.midX - wanted.width / 2).rounded(),
            y: (visible.midY - wanted.height / 2).rounded(),
            width: wanted.width.rounded(),
            height: wanted.height.rounded())

        let backdrop = NSWindow(
            contentRect: backdropFrame, styleMask: [.borderless], backing: .buffered, defer: false)
        backdrop.isOpaque = true
        backdrop.hasShadow = false
        // **`.screenSaver`, not `.floating`.** The backdrop is the entire privacy guarantee, and the
        // frame it guards is written to a file on disk. At `.floating` it only clears *this*
        // process's windows: another application's panel, notification or overlay sits at the same
        // level or above it, lands inside the captured rectangle, and is then somebody's real screen
        // in a PNG. Measured rather than assumed — two frames of an earlier run of these render
        // harnesses came back with a browser's window furniture and its coloured reflections along
        // the edge. Anything left
        // floating above this window ends up in the capture, so it goes above the levels an ordinary
        // application window can reach.
        backdrop.level = .screenSaver
        backdrop.contentView = {
            let view = NSImageView(frame: NSRect(origin: .zero, size: backdropFrame.size))
            view.image = desktop
            view.imageScaling = .scaleAxesIndependently
            return view
        }()
        backdrop.orderFrontRegardless()

        let panelFrame = NSRect(
            x: backdropFrame.minX + inset, y: backdropFrame.minY + inset,
            width: surface, height: height)
        // **The shipped surface's shape, not a stand-in for it.** The same borderless non-activating
        // panel `SearchBarWindow.present` puts up: transparent ground, no window shadow — each panel
        // casts its own, inside the window — and the light pin that keeps the type dark on a Dark Mac.
        //
        // The level is the one deliberate difference: it has to clear the backdrop above, which sits
        // at `.screenSaver`, and window level is not something a golden can see.
        let window = NSPanel(
            contentRect: panelFrame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.isReleasedWhenClosed = false
        InkGlass.pin(window)
        window.level = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)

        let root = NSView(frame: NSRect(origin: .zero, size: panelFrame.size))
        root.autoresizingMask = [.width, .height]

        let hosting = NSHostingView(
            rootView: SearchBarView(query: query, results: model))
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)
        window.contentView = root
        window.orderFrontRegardless()

        // A run loop, not a sleep: the material samples the desktop through the window server, the
        // thumbnails decode on a detached task, and SwiftUI settles its layout — none of which
        // happens on a blocked thread.
        spin(seconds: 1.6)

        if scrollToEnd {
            let scroller = try XCTUnwrap(Self.verticalScroller(in: root))

            // **The faded strip still scrolls.** The bottom edge's fade is a mask, and a mask that
            // swallowed the pointer would make the one strip that says "there is more below" the one
            // strip you cannot scroll from. Driven as a real wheel event through the window, landing
            // inside the fade, and asserted on the clip view that had to move.
            // **The faded strip is still the scroll view's.** A wheel event is routed by AppKit's
            // `hitTest`, so the question the fade raises — does a mask take the strip that advertises
            // "more below" out of the pointer's reach? — is answered by asking who owns that point.
            // A layer mask must not, and this is what proves it rather than assuming it.
            let body = scroller.convert(scroller.bounds, to: nil)
            func owner(at point: NSPoint) -> NSView? {
                let hit = window.contentView?.hitTest(point)
                print("[fade] \(point) → \(hit.map { String(describing: type(of: $0)) } ?? "nothing")")
                return hit
            }
            func isInsideBody(_ view: NSView?) -> Bool {
                var node = view
                while let current = node {
                    if current === scroller { return true }
                    node = current.superview
                }
                return false
            }
            let middle = owner(at: NSPoint(x: body.midX, y: body.midY))
            let inFade = owner(at: NSPoint(x: body.midX, y: body.minY + SearchLayout.scrollFadeHeight / 2))
            // The control: the unmasked middle of the body has to belong to the scroll view, or the
            // probe is measuring the harness rather than the fade.
            XCTAssertTrue(isInsideBody(middle), "the harness is not probing the results body at all")
            XCTAssertTrue(
                isInsideBody(inFade),
                "the bottom fade is not part of the scroll view for hit testing — the mask is eating "
                    + "the pointer in exactly the strip that advertises more below")

            // …and then all the way to the end, which is the state worth looking at: the fade has to
            // fall on the spare room under the last row rather than on its source line.
            scroller.scrollToEnd()
            spin(seconds: 0.8)
        }

        let url = directory.appendingPathComponent("\(name).png")
        if !capture(rect: backdropFrame, on: screen, to: url) {
            // `screencapture` refuses a rect while the display is asleep or locked, which is a
            // property of the machine and not of the surface. Composite the same frame offline
            // instead: the panel's own bitmap is the real one — scrim, edge, shadow, type, layout,
            // decoded thumbnails — and only the *desktop blur* under it is modelled, with exactly
            // the material opacity and tint `InkGlass` measured. That is the same model
            // `SearchSurfaceTests` asserts the contrast against.
            try compose(
                hosting: hosting, panelOrigin: NSPoint(x: inset, y: inset),
                desktop: desktop, size: backdropFrame.size, to: url)
        }

        window.orderOut(nil)
        backdrop.orderOut(nil)
        spin(seconds: 0.2)
        return url.path
    }

    @MainActor
    private func spin(seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.02))
        }
    }

    /// `screencapture -R`, over the rectangle the backdrop window fully covers.
    ///
    /// A rectangle and not the screen: the machine this runs on has the user's own work open, and a
    /// full-screen grab of it is not something a test may take. The rect is the backdrop's, which is
    /// opaque and on top, so the frame contains nothing but this harness's windows.
    /// Returns false when the window server refused — a locked or sleeping display — so the caller
    /// can fall back rather than fail. A missing frame is a failure; an unavailable screen is not.
    @discardableResult
    private func capture(rect: NSRect, on screen: NSScreen, to url: URL) -> Bool {
        // `screencapture` measures from the top-left of the primary display; AppKit from the
        // bottom-left of the whole desktop space.
        let primaryHeight = NSScreen.screens.first?.frame.maxY ?? screen.frame.maxY
        let top = primaryHeight - rect.maxY

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        process.arguments = [
            "-x", "-o",
            "-R\(Int(rect.minX)),\(Int(top)),\(Int(rect.width)),\(Int(rect.height))",
            url.path,
        ]
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return false
        }
        process.waitUntilExit()
        return process.terminationStatus == 0
            && FileManager.default.fileExists(atPath: url.path)
    }

    // MARK: - Offline composite

    /// The same frame, composited without the window server: desktop, frosted where the glass is,
    /// the panel's layer on top.
    ///
    /// The panel is captured with `CALayer.render(in:)` and **not** `cacheDisplay(in:to:)`: the
    /// latter fills the rect with the window's background before drawing, which turns a transparent
    /// borderless window into an opaque white card and hides the desktop the whole exercise is about
    /// judging. Rendered at 2×, because the point is to look at type.
    @MainActor
    private func compose(
        hosting: NSView, panelOrigin: NSPoint, desktop: NSImage, size: NSSize, to url: URL
    ) throws {
        let scale: CGFloat = 2
        let rep = try XCTUnwrap(
            NSBitmapImageRep(
                bitmapDataPlanes: nil,
                pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale),
                bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                colorSpaceName: .calibratedRGB, bytesPerRow: 0, bitsPerPixel: 0))
        rep.size = size
        let context = try XCTUnwrap(NSGraphicsContext(bitmapImageRep: rep))

        // Where the glass actually is, read off the real view tree rather than re-derived from the
        // layout constants — the one source that cannot drift out of agreement with the view.
        let materials = Self.materialFrames(in: hosting, root: hosting)
        let blurred = Self.blurred(desktop, radius: 24)
        let full = NSRect(origin: .zero, size: size)

        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context

        desktop.draw(in: full)
        for frame in materials {
            let placed = frame.offsetBy(dx: panelOrigin.x, dy: panelOrigin.y)
            NSGraphicsContext.saveGraphicsState()
            NSBezierPath(
                roundedRect: placed,
                xRadius: InkGlass.cornerRadius, yRadius: InkGlass.cornerRadius
            ).addClip()
            blurred.draw(in: full)
            NSColor(
                calibratedWhite: InkGlass.measuredMaterialTint,
                alpha: InkGlass.measuredMaterialOpacity
            ).setFill()
            placed.fill()
            NSGraphicsContext.restoreGraphicsState()
        }

        // The panel's own pixels, transparency intact. An `.behindWindow` `NSVisualEffectView`
        // renders as nothing here, which is exactly right: the frosting above is that layer.
        if let layer = hosting.layer {
            let cg = context.cgContext
            cg.saveGState()
            cg.translateBy(x: panelOrigin.x, y: panelOrigin.y + hosting.bounds.height)
            cg.scaleBy(x: 1, y: -1)
            layer.render(in: cg)
            cg.restoreGState()
        }

        NSGraphicsContext.restoreGraphicsState()
        try XCTUnwrap(rep.representation(using: .png, properties: [:])).write(to: url)
    }

    /// The panel's own vertical scroll view — the tallest one whose content overflows it.
    ///
    /// Found by walking the tree rather than held onto, because the view SwiftUI builds is the one
    /// worth driving: the chip rows are scroll views too, and they scroll the other way.
    private static func verticalScroller(in view: NSView) -> NSScrollView? {
        var found: [NSScrollView] = []
        func walk(_ node: NSView) {
            if let scroll = node as? NSScrollView,
                let document = scroll.documentView,
                document.frame.height > scroll.contentView.bounds.height + 1
            {
                found.append(scroll)
            }
            node.subviews.forEach(walk)
        }
        walk(view)
        return found.max { $0.contentView.bounds.height < $1.contentView.bounds.height }
    }

    /// Every `NSVisualEffectView` in the tree, in `root`'s coordinates. One per glass panel.
    private static func materialFrames(in view: NSView, root: NSView) -> [NSRect] {
        var frames: [NSRect] = []
        if view is NSVisualEffectView { frames.append(view.convert(view.bounds, to: root)) }
        for subview in view.subviews { frames += materialFrames(in: subview, root: root) }
        return frames
    }

    private static func blurred(_ image: NSImage, radius: Double) -> NSImage {
        guard let tiff = image.tiffRepresentation, let input = CIImage(data: tiff),
            let filter = CIFilter(name: "CIGaussianBlur")
        else { return image }
        filter.setValue(input.clampedToExtent(), forKey: kCIInputImageKey)
        filter.setValue(radius, forKey: kCIInputRadiusKey)
        guard let output = filter.outputImage?.cropped(to: input.extent) else { return image }
        let rep = NSCIImageRep(ciImage: output)
        let result = NSImage(size: rep.size)
        result.addRepresentation(rep)
        return result
    }
}

extension NSScrollView {
    /// Scrolls to the very bottom of the document, whichever way round the document is flipped.
    @MainActor
    fileprivate func scrollToEnd() {
        guard let document = documentView else { return }
        let clip = contentView.bounds.height
        let y = document.isFlipped ? document.frame.height - clip : 0
        contentView.scroll(to: NSPoint(x: 0, y: y))
        reflectScrolledClipView(contentView)
    }
}

// MARK: - Fabricated data

/// Everything the harness draws. **All of it is invented** — no row here came from the user's
/// capture database, and the pictures are generated on the spot.
@MainActor
enum Fixtures {

    enum Desktop: String {
        case black, white, midGrey
    }

    /// A synthetic desktop. Not a photograph and not the user's wallpaper: the two extremes are what
    /// the contrast floor is set by, and the mid-grey is a stand-in for an ordinary one.
    static func desktopImage(_ kind: Desktop) -> NSImage {
        let size = NSSize(width: 1600, height: 1200)
        return NSImage(size: size, flipped: false) { rect in
            switch kind {
            case .black:
                NSColor.black.setFill()
                rect.fill()
            case .white:
                NSColor.white.setFill()
                rect.fill()
            case .midGrey:
                // A gradient with some structure, so the blur has something to blur and the glass
                // reads as glass rather than as a flat tint.
                let gradient = NSGradient(colors: [
                    NSColor(calibratedRed: 0.16, green: 0.20, blue: 0.26, alpha: 1),
                    NSColor(calibratedRed: 0.55, green: 0.58, blue: 0.62, alpha: 1),
                    NSColor(calibratedRed: 0.24, green: 0.26, blue: 0.30, alpha: 1),
                ])!
                gradient.draw(in: rect, angle: 35)
                NSColor.white.withAlphaComponent(0.10).setFill()
                for index in 0..<9 {
                    let x = rect.width * CGFloat(index) / 9
                    NSBezierPath(ovalIn: NSRect(x: x, y: rect.height * 0.2, width: 180, height: 180)).fill()
                }
            }
            return true
        }
    }

    /// Writes a handful of fake "screenshots" to disk so the real `FrameLoader` decode path is the
    /// one under test rather than a stand-in.
    static func thumbnails(in directory: URL) throws -> [String] {
        let hues: [NSColor] = [
            .init(calibratedRed: 0.95, green: 0.96, blue: 0.97, alpha: 1),
            .init(calibratedRed: 0.12, green: 0.13, blue: 0.16, alpha: 1),
            .init(calibratedRed: 0.90, green: 0.93, blue: 0.99, alpha: 1),
            .init(calibratedRed: 0.99, green: 0.95, blue: 0.90, alpha: 1),
        ]
        var paths: [String] = []
        for (index, hue) in hues.enumerated() {
            let size = NSSize(width: 1200, height: 800)
            let image = NSImage(size: size, flipped: false) { rect in
                hue.setFill()
                rect.fill()
                // Some furniture, so a thumbnail reads as a screenshot rather than a swatch.
                let ink = hue.brightnessComponent > 0.5 ? NSColor.black : NSColor.white
                ink.withAlphaComponent(0.08).setFill()
                NSRect(x: 0, y: rect.height - 60, width: rect.width, height: 60).fill()
                ink.withAlphaComponent(0.14).setFill()
                for row in 0..<9 {
                    let y = rect.height - 140 - CGFloat(row) * 54
                    let width = rect.width * (0.3 + CGFloat((row * 37) % 60) / 100)
                    NSRect(x: 70, y: y, width: width, height: 20).fill()
                }
                return true
            }
            let url = directory.appendingPathComponent("thumb-\(index).png")
            let data = NSBitmapImageRep(data: image.tiffRepresentation!)!
                .representation(using: .png, properties: [:])!
            try data.write(to: url)
            paths.append(url.path)
        }
        return paths
    }

    static func frame(id: Int64, path: String?, app: String, title: String?, at: Double) -> RewindFrame? {
        guard let path else { return nil }
        return RewindFrame(
            id: id, capturedAt: at, appName: app, bundleId: nil, windowTitle: title,
            ocrText: nil, imagePath: path)
    }

    static func moment(
        id: Int64, title: String, app: String, minutesAgo: Double, path: String?
    ) -> SearchMoment {
        let at = Date().timeIntervalSince1970 - minutesAgo * 60
        return SearchMoment(
            rowId: id,
            title: title,
            source: SearchSource.source(appName: app, windowTitle: title),
            appName: app,
            bundleId: nil,
            capturedAt: at,
            frame: frame(id: id, path: path, app: app, title: title, at: at))
    }

    /// Deliberately varied: a very long title, a very short one, a long domain, an app with no site.
    static let titles: [(String, String, Double)] = [
        ("Comparing M4 Max and RTX 4090 throughput on long-context inference — arc.net", "Arc", 12),
        ("Inbox", "Mail", 41),
        ("SearchBarView.swift — context-for-claude", "Cursor", 63),
        ("Checkout — shop.flixbus.com", "Google Chrome", 190),
        ("Statement — now.hdfcbank.example.com", "Arc", 1_500),
        ("Downloads", "Finder", 1_900),
        ("Benchmarks · archit-lal.github.example.io", "Arc", 2_600),
        ("EMOTIV Launcher", "EMOTIV Launcher", 3_100),
        ("System Settings", "System Settings", 3_400),
        ("A window whose title runs on well past anything a two-hundred-and-thirty point card could ever hold", "Cursor", 4_400),
        ("Docs — duckduckgo.com", "Arc", 5_900),
        ("Context for Claude", "Context for Claude", 8_800),
    ]

    static func twelve(thumbnails: [String]) -> SearchResultsModel {
        let moments = titles.enumerated().map { index, entry in
            moment(
                id: Int64(index + 1), title: entry.0, app: entry.1, minutesAgo: entry.2,
                // Every fourth card has no picture, which is a real state (retention unlinks files)
                // and has to look deliberate rather than broken.
                path: index % 4 == 3 ? nil : thumbnails[index % thumbnails.count])
        }
        return SearchResultsModel(
            moments: moments,
            totalCount: 109,
            websites: SearchResultsModel.facetWebsites(moments),
            apps: SearchResultsModel.facetApps(moments))
    }

    /// The same page with the filter block opened, as if the user had pressed `Filter`.
    static func filtersOpen(thumbnails: [String]) -> SearchResultsModel {
        let model = twelve(thumbnails: thumbnails)
        model.toggleFilters()
        return model
    }

    /// A narrowed answer with the block **closed** — the state the header's summary exists for.
    ///
    /// Narrowed through the real `select` calls rather than by constructing a model that merely
    /// looks narrowed, so the header is reporting state the surface actually set.
    static func narrowedButClosed(thumbnails: [String]) -> SearchResultsModel {
        let model = twelve(thumbnails: thumbnails)
        model.select(time: .today)
        model.select(website: "arc.net")
        return model
    }

    /// The first `count` of the same fabricated moments — the sparse states, where the panel has to
    /// contain everything it has and therefore must show no fade at all.
    static func few(_ count: Int, thumbnails: [String]) -> SearchResultsModel {
        let moments = titles.prefix(count).enumerated().map { index, entry in
            moment(
                id: Int64(index + 1), title: entry.0, app: entry.1, minutesAgo: entry.2,
                path: thumbnails[index % thumbnails.count])
        }
        return SearchResultsModel(
            moments: Array(moments), totalCount: count,
            websites: SearchResultsModel.facetWebsites(Array(moments)),
            apps: SearchResultsModel.facetApps(Array(moments)))
    }

    /// A hundred cards — thirty-four rows, far past anything the panel can hold. The state the
    /// bottom edge has to keep saying "there is more below" in, all the way down.
    ///
    /// The same dozen fabricated titles cycled, with the capture times marching backwards, so no new
    /// invented content is introduced to make the grid longer.
    static func hundred(thumbnails: [String]) -> SearchResultsModel {
        let moments = (0..<100).map { index -> SearchMoment in
            let entry = titles[index % titles.count]
            return moment(
                id: Int64(index + 1), title: entry.0, app: entry.1,
                minutesAgo: entry.2 + Double(index) * 7,
                path: index % 4 == 3 ? nil : thumbnails[index % thumbnails.count])
        }
        return SearchResultsModel(
            moments: moments, totalCount: 100,
            websites: SearchResultsModel.facetWebsites(moments),
            apps: SearchResultsModel.facetApps(moments))
    }

    static func one(thumbnails: [String]) -> SearchResultsModel {
        let moment = moment(
            id: 1, title: "Invoice 2026-07 — now.hdfcbank.example.com", app: "Arc", minutesAgo: 1_450,
            path: thumbnails[0])
        return SearchResultsModel(
            moments: [moment], totalCount: 1,
            websites: SearchResultsModel.facetWebsites([moment]),
            apps: SearchResultsModel.facetApps([moment]))
    }

    static func none() -> SearchResultsModel {
        SearchResultsModel(
            moments: [], totalCount: 0,
            websites: ["arc.net", "shop.flixbus.com"],
            apps: [SearchAppFacet(name: "Arc", bundleId: nil), SearchAppFacet(name: "Cursor", bundleId: nil)])
    }

    /// The state a Mac is in ten minutes after install: nothing captured, so every section is empty.
    static func freshInstall() -> SearchResultsModel {
        SearchResultsModel(moments: [], totalCount: 0, websites: [], apps: [])
    }

    /// Invented spoken lines, deliberately varied in length: one that fits the well in a line, one
    /// that fills it, and one that has to truncate inside it.
    static let lines: [(String, SegmentSource, String?, Double)] = [
        ("I'll send the invoice over before Friday, the one from last month", .mic, "zoom.us", 22),
        ("sounds good — can you cc finance on it as well", .system, "zoom.us", 24),
        ("no, the other invoice, the one with the wrong billing address on it that we had to reissue "
            + "after the address change went through and nobody told accounts", .system, nil, 130),
        ("remind me to chase the invoice", .mic, "Slack", 900),
    ]

    static func spoken(id: Int64, index: Int) -> SearchMoment {
        let entry = lines[index % lines.count]
        return SearchMoment(
            line: ScreenSearchQueries.SpokenLine(
                id: id,
                sessionId: Int64(index + 1),
                startedAt: Date().timeIntervalSince1970 - entry.3 * 60,
                source: entry.1,
                text: entry.0,
                appHint: entry.2))
    }

    /// Both halves on one page, merged by the real ranking rather than by the order they are listed
    /// here — the harness must show what ships, not a hand-arranged page.
    static func mixed(thumbnails: [String]) -> SearchResultsModel {
        let screens = titles.prefix(8).enumerated().map { index, entry in
            moment(
                id: Int64(index + 1), title: entry.0, app: entry.1, minutesAgo: entry.2,
                path: index % 4 == 3 ? nil : thumbnails[index % thumbnails.count])
        }
        let spokenLines = (0..<4).map { spoken(id: Int64(200 + $0), index: $0) }
        let merged = SearchRanking.merge(
            screens: Array(screens), conversations: spokenLines, query: "invoice",
            limit: SearchResultsModel.pageSize)
        return SearchResultsModel(
            moments: merged,
            totalCount: merged.count,
            websites: SearchResultsModel.facetWebsites(Array(screens)),
            apps: SearchResultsModel.facetApps(Array(screens)))
    }

    /// Every card's picture is gone. The worst case for the placeholder.
    static func missingPictures() -> SearchResultsModel {
        let moments = titles.prefix(6).enumerated().map { index, entry in
            moment(id: Int64(index + 1), title: entry.0, app: entry.1, minutesAgo: entry.2, path: nil)
        }
        return SearchResultsModel(
            moments: Array(moments), totalCount: 6,
            websites: SearchResultsModel.facetWebsites(Array(moments)),
            apps: SearchResultsModel.facetApps(Array(moments)))
    }
}
