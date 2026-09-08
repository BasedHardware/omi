import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the System Settings spotlight over a **synthetic** pane and writes the frames out for a
/// person to look at.
///
/// **Skipped unless `CONTEXT_SPOTLIGHT_RENDER=1`.** It writes files, and it exists to be run by hand
/// while working on the drawing; the claims that have to hold every time are in
/// `SettingsSpotlightTests`, which is pure and hermetic.
///
/// Two rules it obeys:
///
/// - **Synthetic, never real.** The pane underneath is drawn here out of rectangles. Nothing opens
///   System Settings, nothing screenshots the desktop, and nothing of the user's is ever in a frame.
/// - **`ImageRenderer` over the shipping view.** The canvas is a pure function of a scene and two
///   phases by construction, which is what makes this possible at all — the overlay otherwise exists
///   for about four seconds in the middle of somebody's first run.
final class SettingsSpotlightRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_SPOTLIGHT_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "spotlight-renders")
    }

    private static let display = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
    private static var space: ScreenSpace { ScreenSpace(displays: [display]) }

    @MainActor
    func testRenderTheSpotlight() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_SPOTLIGHT_RENDER"] == "1",
            "render harness; set CONTEXT_SPOTLIGHT_RENDER=1 to run it")

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let drag = try XCTUnwrap(Self.dragScene(), "the drag scene must resolve")
        // Across the hand's whole travel, so the motion is evident frame to frame rather than
        // asserted in a comment.
        for (index, phase) in [0.06, 0.22, 0.30, 0.45, 0.60, 0.72, 0.80, 0.93].enumerated() {
            try write(
                Self.frame(scene: drag, phase: phase, handPhase: phase),
                to: directory, named: String(format: "drag-%02d-phase-%.2f", index, phase))
        }

        // Reduce Motion: one still frame, and it has to carry the whole instruction on its own.
        try write(
            Self.frame(
                scene: drag, phase: SettingsSpotlightCanvas.stillPhase,
                handPhase: SettingsSpotlightCanvas.stillHandPhase),
            to: directory, named: "drag-reduce-motion-still")

        // The other two tiers, so a change to the drag cannot quietly break them.
        try write(
            Self.frame(scene: try XCTUnwrap(Self.clickScene()), phase: 0.5, handPhase: 0.5),
            to: directory, named: "click-on-a-listed-row")
        try write(
            Self.frame(scene: try XCTUnwrap(Self.framingScene()), phase: 0.5, handPhase: 0.5),
            to: directory, named: "framing-only-the-window-is-known")

        print("[spotlight] frames written to \(directory.path)")
    }

    // MARK: Scenes

    static func dragScene() -> SettingsSpotlightScene? {
        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [PaneFixture.dragPane()],
            windowFrame: PaneFixture.dragPaneWindow, space: space)
        guard case .pointing(let target) = guidance else { return nil }
        return SettingsSpotlightScene.make(
            target: target,
            caption: PermissionChoreography.caption(
                for: target.gesture, appName: PaneFixture.appName, isOn: false, listed: false),
            display: display, space: space)
    }

    static func clickScene() -> SettingsSpotlightScene? {
        let target = SettingsSpotlightTarget(
            row: CGRect(x: 611, y: 225, width: 442, height: 40),
            toggle: CGRect(x: 1_009, y: 237, width: 36, height: 16), isOn: false,
            focus: CGRect(x: 999, y: 232, width: 56, height: 30),
            area: PaneFixture.dragPaneList, list: PaneFixture.dragPaneList, isListed: true,
            gesture: .click, window: PaneFixture.dragPaneWindow)
        return SettingsSpotlightScene.make(
            target: target, caption: "Click this switch to turn on \(PaneFixture.appName)",
            display: display, space: space)
    }

    static func framingScene() -> SettingsSpotlightScene? {
        SettingsSpotlightScene.make(
            framing: SettingsWindowFrame(
                window: PaneFixture.dragPaneWindow,
                instruction: "In System Settings, open Privacy & Security ▸ Screen & System Audio "
                    + "Recording and switch on \(PaneFixture.appName)."),
            display: display, space: space)
    }

    // MARK: Rendering

    @MainActor
    private static func frame(scene: SettingsSpotlightScene, phase: Double, handPhase: Double)
        -> some View
    {
        ZStack {
            SyntheticSettingsPane()
            SettingsSpotlightCanvas(scene: scene, phase: phase, handPhase: handPhase)
        }
        .frame(width: display.appKitFrame.width, height: display.appKitFrame.height)
    }

    @MainActor
    private func write(_ view: some View, to directory: URL, named name: String) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.cgImage, "\(name) did not render")
        let bitmap = NSBitmapImageRep(cgImage: image)
        let data = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
        try data.write(to: directory.appendingPathComponent("\(name).png"))
    }
}

/// A System Settings-shaped pane, drawn out of rectangles.
///
/// Deliberately a rough likeness and deliberately never presented as System Settings: it exists only
/// so the overlay can be judged against something the right shape and the right lightness. Its
/// geometry is `PaneFixture`'s, so what the overlay is drawn over is the same rects the scene was
/// solved from — which is the only way a frame can show a misalignment rather than hide one.
struct SyntheticSettingsPane: View {
    var body: some View {
        Canvas { context, size in
            // Desktop.
            context.fill(
                Path(CGRect(origin: .zero, size: size)),
                with: .linearGradient(
                    Gradient(colors: [Color(white: 0.18), Color(white: 0.07)]),
                    startPoint: .zero, endPoint: CGPoint(x: size.width, y: size.height)))

            let window = PaneFixture.dragPaneWindow
            context.fill(
                Path(roundedRect: window, cornerRadius: 12), with: .color(Color(white: 0.94)))
            // Sidebar.
            context.fill(
                Path(
                    roundedRect: CGRect(
                        x: window.minX, y: window.minY, width: 220, height: window.height),
                    cornerRadius: 12),
                with: .color(Color(white: 0.90)))
            for index in 0..<9 {
                context.fill(
                    Path(
                        roundedRect: CGRect(
                            x: window.minX + 16, y: window.minY + 60 + CGFloat(index) * 34,
                            width: 150, height: 14),
                        cornerRadius: 4),
                    with: .color(Color(white: 0.72)))
            }
            // Pane header.
            context.fill(
                Path(
                    roundedRect: CGRect(x: 603, y: 74, width: 300, height: 20), cornerRadius: 5),
                with: .color(Color(white: 0.55)))
            context.fill(
                Path(
                    roundedRect: CGRect(x: 603, y: 108, width: 420, height: 13), cornerRadius: 4),
                with: .color(Color(white: 0.72)))

            // The list, and the rows in it.
            let list = PaneFixture.dragPaneList
            context.fill(Path(roundedRect: list, cornerRadius: 9), with: .color(.white))
            context.stroke(
                Path(roundedRect: list, cornerRadius: 9), with: .color(Color(white: 0.83)),
                style: StrokeStyle(lineWidth: 1))
            for index in 0..<3 {
                let y = list.minY + CGFloat(index) * 40
                row(in: &context, at: CGRect(x: list.minX, y: y, width: list.width, height: 40), on: true)
                if index < 2 {
                    context.stroke(
                        Path { $0.move(to: CGPoint(x: list.minX + 12, y: y + 40))
                            $0.addLine(to: CGPoint(x: list.maxX - 12, y: y + 40)) },
                        with: .color(Color(white: 0.90)), style: StrokeStyle(lineWidth: 1))
                }
            }

            // The loose row below the list — macOS 26's own dashed affordance, which is *theirs*, and
            // is exactly why ours is blue and sits outside it rather than replacing it.
            let stray = PaneFixture.dragPaneStrayRow
            context.stroke(
                Path(roundedRect: stray, cornerRadius: 7), with: .color(Color(white: 0.62)),
                style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
            row(in: &context, at: stray, on: false)
        }
    }

    /// One row: an icon, a name and a switch.
    private func row(in context: inout GraphicsContext, at rect: CGRect, on: Bool) {
        context.fill(
            Path(roundedRect: CGRect(x: rect.minX + 12, y: rect.midY - 10, width: 20, height: 20),
                cornerRadius: 5),
            with: .color(Color(white: 0.75)))
        context.fill(
            Path(roundedRect: CGRect(x: rect.minX + 42, y: rect.midY - 6, width: 150, height: 12),
                cornerRadius: 4),
            with: .color(Color(white: 0.45)))
        let track = CGRect(x: rect.maxX - 56, y: rect.midY - 8, width: 36, height: 16)
        context.fill(
            Path(roundedRect: track, cornerRadius: 8),
            with: .color(on ? Color(red: 0.20, green: 0.48, blue: 0.93) : Color(white: 0.80)))
        context.fill(
            Path(
                ellipseIn: CGRect(
                    x: on ? track.maxX - 15 : track.minX + 1, y: track.minY + 1, width: 14,
                    height: 14)),
            with: .color(.white))
    }
}
