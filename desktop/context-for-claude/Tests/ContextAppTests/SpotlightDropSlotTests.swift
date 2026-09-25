import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

// MARK: - The dotted outline goes round one row, never round the list
//
//  Reported with two screenshots of the same System Settings pane. The one marked good: a single row
//  sitting below the list, outlined by a dashed rounded rectangle around **just that one row**, with
//  a short caption and an arrow pointing up into the list. The one marked bad: the *entire* list
//  boxed in one big dashed rectangle. "With that very subbox being highlighted in a dotted window.
//  Not the entire thing."
//
//  The overlay drew the bad one. `SettingsSpotlightScene.destination` was the list — correctly, it is
//  where the row has to end up — and `drawRegions` dashed and tinted whatever `destination` was. So a
//  pane with a dozen applications in it got one dashed rectangle around all of them.
//
//  `dropSlot` is the fix and this file is what holds it: a row-height strip at the edge of the list
//  the row is arriving from, dashed instead of the list. `destination` is unchanged and still aims
//  the arrow and places the caption, which is why `SettingsSpotlightTests` needed no adjustment —
//  what changed is only what is drawn round.

final class SpotlightDropSlotTests: XCTestCase {
    private let display = DisplayGeometry(
        appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982), backingScaleFactor: 2)
    private var space: ScreenSpace { ScreenSpace(displays: [display]) }

    /// The real decision, over the real pane fixture, into the real scene builder — the same route
    /// `SpotlightRegionTests` uses, so the two cannot describe different scenes.
    private func dragScene() -> SettingsSpotlightScene? {
        let guidance = PermissionChoreography.guidance(
            for: .screen, appName: PaneFixture.appName, windows: [PaneFixture.dragPane()],
            windowFrame: PaneFixture.dragPaneWindow, space: space)
        guard case .pointing(let target) = guidance else { return nil }
        return SettingsSpotlightScene.make(
            target: target,
            caption: PermissionChoreography.caption(
                for: target.gesture, appName: PaneFixture.appName, isOn: false, listed: false),
            display: display, space: space, subject: PaneFixture.appName)
    }

    // MARK: The model

    /// **One row's worth of list, and not the list.**
    ///
    /// Stated as arithmetic against the fixture rather than as a rendered impression: the slot is
    /// inside the list, the height of the row being dragged, and a small fraction of the area the
    /// old dashed rectangle covered.
    func testTheDropTargetIsOneRowRatherThanTheWholeList() throws {
        let scene = try XCTUnwrap(dragScene())
        let list = try XCTUnwrap(scene.destination)
        let slot = try XCTUnwrap(scene.dropSlot)
        let source = try XCTUnwrap(scene.source)

        XCTAssertTrue(list.contains(slot), "the slot has to be somewhere inside the list")
        XCTAssertEqual(
            slot.height, source.height, accuracy: 1,
            "the slot is the height of the row arriving in it — that is what makes it read as a row")
        XCTAssertLessThan(
            slot.height * slot.width, list.height * list.width * 0.25,
            "a 'slot' covering a quarter of the list is the whole-list rectangle the report was "
                + "about, wearing a different name")
    }

    /// The slot goes at the edge the row is coming from — the foot for a row loose below the pane,
    /// the head for one above it — because that is the edge the arrow crosses.
    func testTheSlotSitsAtTheEdgeTheRowIsArrivingFrom() {
        let list = CGRect(x: 100, y: 200, width: 400, height: 300)

        let fromBelow = SettingsSpotlightScene.landingSlot(
            in: list, arrivingFrom: CGRect(x: 110, y: 600, width: 380, height: 32))
        XCTAssertEqual(fromBelow.maxY, list.maxY, accuracy: 0.001, "it lands at the foot")

        let fromAbove = SettingsSpotlightScene.landingSlot(
            in: list, arrivingFrom: CGRect(x: 110, y: 40, width: 380, height: 32))
        XCTAssertEqual(fromAbove.minY, list.minY, accuracy: 0.001, "and at the head from above")
    }

    /// Nothing is ever drawn outside the thing it is a slot in. A list shorter than a row, or a
    /// source rect the Accessibility API answered nonsense for, still yields something inside the
    /// list rather than a strip hanging off it.
    func testTheSlotIsAlwaysInsideTheList() {
        let cases: [(String, CGRect, CGRect)] = [
            ("a list shorter than one row", CGRect(x: 0, y: 0, width: 300, height: 12),
             CGRect(x: 0, y: 400, width: 300, height: 40)),
            ("a source taller than the list", CGRect(x: 0, y: 0, width: 300, height: 90),
             CGRect(x: 0, y: 400, width: 300, height: 900)),
            ("a bare label frame", CGRect(x: 0, y: 0, width: 300, height: 300),
             CGRect(x: 10, y: 400, width: 146, height: 2)),
            ("a narrow list", CGRect(x: 0, y: 0, width: 8, height: 300),
             CGRect(x: 0, y: 400, width: 8, height: 40)),
        ]
        for (name, list, source) in cases {
            let slot = SettingsSpotlightScene.landingSlot(in: list, arrivingFrom: source)
            XCTAssertTrue(
                list.insetBy(dx: -0.5, dy: -0.5).contains(slot),
                "\(name): the slot \(slot) escaped the list \(list)")
            XCTAssertGreaterThan(slot.width, 0, "\(name): an empty slot draws nothing")
            XCTAssertGreaterThan(slot.height, 0, "\(name): an empty slot draws nothing")
        }
    }

    /// The arrow still lands where the thing goes: inside the list, and inside the slot within it.
    /// A drag arrow that stops short of its target is describing a different gesture.
    func testTheArrowLandsInsideTheSlotAndTheListBothTogether() throws {
        let scene = try XCTUnwrap(dragScene())
        let arrow = try XCTUnwrap(scene.arrow)
        let slot = try XCTUnwrap(scene.dropSlot)
        let list = try XCTUnwrap(scene.destination)

        XCTAssertTrue(slot.insetBy(dx: -1, dy: -1).contains(arrow.tip))
        XCTAssertTrue(list.contains(arrow.tip))
        XCTAssertLessThan(arrow.tip.y, arrow.tail.y, "up the pane")
    }

    /// The glow is not a second highlight on the same rect. `drawFocusGlow` refuses to ring anything
    /// already dashed, and this is the fact that refusal depends on — a drag's focus *is* its slot.
    func testADragGlowsNothingSeparateFromTheSlotItAlreadyDashes() throws {
        let scene = try XCTUnwrap(dragScene())
        XCTAssertEqual(
            scene.focus, scene.dropSlot,
            "a drag whose focus is the whole list would put a white ring back around every row")
    }

    /// A pane we are not listed in at all points at **+**, and still marks a row-sized landing rather
    /// than boxing the list. Same complaint, the other gesture.
    func testTheNotListedGestureAlsoMarksARowRatherThanTheList() throws {
        let list = CGRect(x: 603, y: 145, width: 460, height: 300)
        let add = CGRect(x: 615, y: 470, width: 24, height: 24)
        let target = try XCTUnwrap(
            PermissionChoreography.notListedTarget(
                SettingsRowLocator.NotListed(
                    area: CGRect(x: 603, y: 120, width: 460, height: 380), list: list, add: add,
                    strayRow: nil),
                window: PaneFixture.dragPaneWindow))
        let scene = try XCTUnwrap(
            SettingsSpotlightScene.make(
                target: target, caption: "Click +", display: display, space: space))

        let slot = try XCTUnwrap(scene.dropSlot)
        XCTAssertTrue(list.contains(slot))
        XCTAssertLessThan(slot.height, list.height / 2)
        XCTAssertEqual(scene.focus, add, "the thing to press is still the + button")
    }

    // MARK: The pixels

    /// **The complaint, answered on the rendered frame.**
    ///
    /// Model assertions can only say the slot is small; they cannot say the list stopped being
    /// outlined, because "what gets dashed" lives in the drawing. So this renders the shipping canvas
    /// over the shipping scene and looks: no accent-coloured pixel anywhere in the top half of the
    /// list, and accent-coloured pixels along the slot's own edge.
    ///
    /// Reverting `drawRegions` to dash `destination` fails the first half immediately — which is what
    /// makes this a regression test rather than a description.
    @MainActor
    func testTheListIsNotOutlinedAndTheSlotIs() throws {
        let scene = try XCTUnwrap(dragScene())
        let list = try XCTUnwrap(scene.destination)
        let slot = try XCTUnwrap(scene.dropSlot)
        // Early in the loop: the hand is still over the source row, so nothing is travelling across
        // the list to confuse a pixel count.
        let bitmap = try Self.render(scene, phase: 0.5, handPhase: 0.05)

        let listTop = CGRect(
            x: list.minX, y: list.minY - 14, width: list.width, height: list.height / 2)
        XCTAssertEqual(
            Self.accentPixels(in: listTop, of: bitmap), 0,
            "the list is still being outlined — that is the big dashed rectangle the report was "
                + "about, and it is the one thing this overlay may not draw")

        let slotEdge = CGRect(x: slot.minX, y: slot.minY - 10, width: slot.width, height: 20)
        XCTAssertGreaterThan(
            Self.accentPixels(in: slotEdge, of: bitmap), 20,
            "nothing was drawn round the drop slot, so the overlay now says where the row goes by "
                + "saying nothing at all")
    }

    /// **What travels along the arrow is this application, not a blank rectangle.**
    ///
    /// The pane it lands on is a list of applications; a featureless box arriving in it says a row
    /// goes there without saying whose. The token carries the mark and the name, drawn white on a
    /// dark plate — so a frame mid-carry has both a near-black and a near-white pixel where the hand
    /// is, and a frame before the carry has neither.
    @MainActor
    func testSomethingBearingTheAppTravelsAlongTheArrow() throws {
        let scene = try XCTUnwrap(dragScene())
        let arrow = try XCTUnwrap(scene.arrow)
        XCTAssertEqual(scene.subject, PaneFixture.appName, "the token has to know whose row it is")

        let carrying = DragHandPlan.at(0.5, along: arrow)
        XCTAssertTrue(carrying.isCarrying, "0.5 is mid-travel; this test is aimed at the wrong beat")
        let box = CGRect(
            x: carrying.position.x - 60, y: carrying.position.y - 18, width: 120, height: 36)

        let mid = try Self.render(scene, phase: 0.5, handPhase: 0.5)
        XCTAssertGreaterThan(
            Self.lumaPixels(in: box, of: mid, where: { $0 < 0.25 }), 40,
            "no dark plate where the hand is — nothing is being carried")
        XCTAssertGreaterThan(
            Self.lumaPixels(in: box, of: mid, where: { $0 > 0.85 }), 10,
            "the plate is blank: the mark and the name are what make it this application's row")

        // The negative control: the same box, before the grab. Without it the two counts above could
        // be measuring the pane rather than the token.
        let before = try Self.render(scene, phase: 0.5, handPhase: 0.02)
        XCTAssertLessThan(
            Self.lumaPixels(in: box, of: before, where: { $0 < 0.25 }), 40,
            "the plate is being drawn before the hand has closed on the row")
    }

    // MARK: Rendering

    /// `ImageRenderer` over the shipping canvas, at scale 1 so a point is a pixel and the scene's own
    /// coordinates can be used to sample it. The same technique `SpotlightBrandTests` uses.
    @MainActor
    private static func render(_ scene: SettingsSpotlightScene, phase: Double, handPhase: Double)
        throws -> NSBitmapImageRep
    {
        let renderer = ImageRenderer(
            content: ZStack {
                Color.white
                SettingsSpotlightCanvas(scene: scene, phase: phase, handPhase: handPhase)
            }
            .frame(width: scene.bounds.width, height: scene.bounds.height))
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.cgImage, "the spotlight did not render")
        return try XCTUnwrap(
            NSBitmapImageRep(cgImage: image).converting(to: .sRGB, renderingIntent: .default))
    }

    /// Pixels that are unmistakably the overlay's blue rather than the white ground, the grey scrim
    /// or the black caption plate. Deliberately a wide margin: the dashes are composited over a
    /// blurred dark ribbon, so the exact value moves and only the direction is stable.
    private static func accentPixels(in rect: CGRect, of bitmap: NSBitmapImageRep) -> Int {
        count(in: rect, of: bitmap) { pixel in
            let blue = Double(pixel.blueComponent)
            return blue - Double(pixel.redComponent) > 0.20 && blue > 0.35
        }
    }

    /// Pixels whose brightness satisfies `test`.
    private static func lumaPixels(
        in rect: CGRect, of bitmap: NSBitmapImageRep, where test: @escaping (Double) -> Bool
    ) -> Int {
        count(in: rect, of: bitmap) { pixel in
            test(
                0.2126 * Double(pixel.redComponent) + 0.7152 * Double(pixel.greenComponent)
                    + 0.0722 * Double(pixel.blueComponent))
        }
    }

    /// The sweep itself. Every second pixel in each direction — these are hundreds-of-points regions
    /// and a full sweep costs seconds while finding the same answer.
    private static func count(
        in rect: CGRect, of bitmap: NSBitmapImageRep, where predicate: (NSColor) -> Bool
    ) -> Int {
        var count = 0
        let minX = max(Int(rect.minX), 0)
        let maxX = min(Int(rect.maxX), bitmap.pixelsWide)
        let minY = max(Int(rect.minY), 0)
        let maxY = min(Int(rect.maxY), bitmap.pixelsHigh)
        guard minX < maxX, minY < maxY else { return 0 }
        for x in stride(from: minX, to: maxX, by: 2) {
            for y in stride(from: minY, to: maxY, by: 2) {
                guard let pixel = bitmap.colorAt(x: x, y: y), pixel.alphaComponent > 0.5 else {
                    continue
                }
                if predicate(pixel) { count += 1 }
            }
        }
        return count
    }
}
