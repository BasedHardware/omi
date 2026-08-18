import AppKit
import XCTest

@testable import ContextApp

/// The window *around* the glass — the properties every translucent surface in this app depends on
/// and none of them can see.
///
/// `InkGlassTests` asserts what the panel is made of. Nothing there can catch the other half of the
/// defect: a panel built perfectly and then hosted in a window that paints its own ground. That
/// window renders as an opaque slab with a blur behind it that samples nothing, and every value in
/// the drawing code still reads correct — which is why this is asserted on real `NSWindow`s driven
/// through the production call rather than restated as constants.
///
/// The windows are created with `defer: true` and never ordered front, so nothing here needs a
/// window server and nothing appears on screen.
final class WindowGlassTests: XCTestCase {

    // MARK: - Two grounds

    /// **A glass window paints no ground of its own, whatever kind it is.**
    ///
    /// The whole of it, in two properties. An `NSVisualEffectView` blending `.behindWindow` samples
    /// what is behind the *window*; a window still painting its `backgroundColor` has put an opaque
    /// sheet between the desktop and the blur. Each window is put into the wrong state first — a
    /// solid ground and `isOpaque` — so the assertion is that `wear` *takes it away*, rather than
    /// that a fresh `NSWindow` happened not to have one.
    @MainActor
    func testNoKindOfGlassWindowPaintsAGroundOfItsOwn() {
        for kind in WindowGlass.Kind.allCases {
            let window = Self.makeWindow(kind)
            window.backgroundColor = .white
            window.isOpaque = true

            WindowGlass.wear(window, as: kind)

            XCTAssertFalse(window.isOpaque, "\(kind): an opaque window cannot composite the material")
            XCTAssertEqual(
                window.backgroundColor.alphaComponent, 0, accuracy: 1e-9,
                "\(kind): the window is still painting a ground under the panel, which is the second "
                    + "ground that makes glass read as an opaque slab")
        }
    }

    /// …and the window really does end up with **exactly one** ground: the panel's, at the scrim.
    ///
    /// The two halves measured together, on the real pair of objects a window is made of, because
    /// each half passing on its own is precisely the state the shipped defect was in.
    @MainActor
    func testAWindowHostingTheGlassEndsUpWithExactlyOneGround() throws {
        let window = Self.makeWindow(.titled)
        WindowGlass.wear(window, as: .titled)

        let glass = InkGlassView(
            frame: NSRect(origin: .zero, size: window.frame.size), style: .fullBleed)
        window.contentView = glass
        glass.layoutSubtreeIfNeeded()
        // Passed in rather than read: `NSWorkspace.accessibilityDisplayShouldReduceTransparency` is a
        // machine setting, and a test that sampled it would pass or fail on whose Mac it ran on.
        glass.apply(reduceTransparency: false)

        XCTAssertEqual(
            window.backgroundColor.alphaComponent, 0, accuracy: 1e-9,
            "the window is painting a ground of its own under the panel")
        let ground = try XCTUnwrap(glass.ground.layer?.backgroundColor)
        XCTAssertEqual(
            ground.alpha, InkGlass.scrim, accuracy: 1e-6,
            "the panel's own ground is not the scrim, so the one remaining ground is the wrong one")
        XCTAssertFalse(glass.material.isHidden, "there is no material left to see the desktop through")
    }

    // MARK: - The pin

    /// **The window is pinned light, and the pin has to survive whatever the machine is.**
    ///
    /// On the window and not only on the content view, because the parts of a window this app does
    /// not draw itself read the *window's* appearance: the title bar, the traffic lights, the
    /// scrollers, and the search field's own resolved `labelColor`. Asserted against a window that
    /// has explicitly been put in Dark first, since a test host runs in whichever appearance it
    /// happens to be in and would otherwise pass by coincidence.
    @MainActor
    func testTheWindowIsPinnedLightSoItsOwnChromeConvertsWithTheGlass() {
        for kind in WindowGlass.Kind.allCases {
            let window = Self.makeWindow(kind)
            window.appearance = NSAppearance(named: .darkAqua)

            WindowGlass.wear(window, as: kind)

            XCTAssertEqual(
                window.appearance?.name, InkGlass.appearanceName,
                "\(kind): the window stayed Dark, so its title bar, scrollers and AppKit text will be "
                    + "the system's appearance on a surface that is pinned light")
            XCTAssertEqual(window.effectiveAppearance.name, InkGlass.appearanceName, "\(kind)")
        }
    }

    // MARK: - The shadow

    /// **Exactly one shadow per window — never none, never two.**
    ///
    /// The pairing between this file and `InkGlassStyle` is the claim worth holding, because the two
    /// halves are decided in different files and either mistake is a real one. A floating window that
    /// keeps AppKit's shadow gets a second, tighter, *rectangular* one traced around a frame that is
    /// dozens of points larger than the panel and transparent everywhere else. A titled window whose
    /// panel drew its own would have the window frame's shadow on top of it.
    func testExactlyOneShadowIsDrawnPerWindow() {
        XCTAssertNotNil(
            InkGlassStyle.floating.shadow,
            "a floating panel draws the ambient shadow itself, and this is where it says so")
        XCTAssertFalse(
            WindowGlass.drawsSystemShadow(.floating),
            "a floating window would then have two shadows, one of them around a transparent frame")

        XCTAssertNil(
            InkGlassStyle.fullBleed.shadow,
            "the inside of a titled window must not shadow itself; the frame already does")
        XCTAssertTrue(
            WindowGlass.drawsSystemShadow(.titled),
            "…and with AppKit's turned off as well, a titled glass window would have no shadow at all")
    }

    /// The shadow decision really reaches the window, rather than being a value nothing reads.
    @MainActor
    func testTheShadowDecisionIsAppliedToTheWindow() {
        for kind in WindowGlass.Kind.allCases {
            let window = Self.makeWindow(kind)
            window.hasShadow = !WindowGlass.drawsSystemShadow(kind)

            WindowGlass.wear(window, as: kind)

            XCTAssertEqual(window.hasShadow, WindowGlass.drawsSystemShadow(kind), "\(kind)")
        }
    }

    // MARK: - The title bar

    /// A titled window's chrome gets out of the glass's way: the bar is transparent so the panel runs
    /// edge to edge under it, the title is hidden because these windows say their own name in the
    /// content, and the separator — a hairline drawn straight across the panel — is off.
    @MainActor
    func testATitledGlassWindowLetsThePanelRunUnderItsTitleBar() {
        let window = Self.makeWindow(.titled)
        WindowGlass.wear(window, as: .titled)

        XCTAssertTrue(
            window.titlebarAppearsTransparent,
            "an opaque title bar is a strip of system-coloured chrome across the top of the glass")
        XCTAssertEqual(window.titleVisibility, .hidden)
        XCTAssertEqual(
            window.titlebarSeparatorStyle, .none,
            "the separator is a hairline across the panel, which on glass reads as a crack")
    }

    /// …and a floating window is left alone about it. There is no title bar on a borderless window,
    /// and a `wear` that set title properties there would be stating something it cannot know.
    func testOnlyATitledWindowHasATitleBarToConvert() {
        XCTAssertTrue(WindowGlass.hasTitlebar(.titled))
        XCTAssertFalse(WindowGlass.hasTitlebar(.floating))
    }

    // MARK: -

    /// A window of the shape each kind really ships as. `defer: true` so no window device is created:
    /// every claim here is about properties, and none of them needs a window server.
    @MainActor
    private static func makeWindow(_ kind: WindowGlass.Kind) -> NSWindow {
        let frame = NSRect(x: 0, y: 0, width: 640, height: 480)
        switch kind {
        case .floating:
            return NSWindow(
                contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: true)
        case .titled:
            return NSWindow(
                contentRect: frame,
                styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                backing: .buffered,
                defer: true)
        }
    }
}
