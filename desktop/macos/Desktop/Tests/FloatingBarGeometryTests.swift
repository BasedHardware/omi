import AppKit
import XCTest
@testable import Omi_Computer

final class FloatingBarGeometryTests: XCTestCase {
    private let visibleFrame = NSRect(x: 0, y: 0, width: 1440, height: 900)
    private let compactSize = NSSize(width: 40, height: 14)
    private let voiceSize = NSSize(width: 224, height: 42)
    private let topInset: CGFloat = 40

    func testDefaultPillFrameIsTopCenteredInVisibleFrame() {
        let frame = FloatingControlBarGeometry.defaultPillFrame(
            size: compactSize,
            visibleFrame: visibleFrame,
            topInset: topInset
        )

        XCTAssertEqual(frame.origin.x, 700)
        XCTAssertEqual(frame.origin.y, 846)
        XCTAssertEqual(frame.size, compactSize)
    }

    func testPTTExpansionKeepsCompactPillCenter() {
        let compactFrame = FloatingControlBarGeometry.defaultPillFrame(
            size: compactSize,
            visibleFrame: visibleFrame,
            topInset: topInset
        )

        let voiceFrame = FloatingControlBarGeometry.pushToTalkFrame(
            currentFrame: compactFrame,
            expanded: true,
            draggable: false,
            visibleFrame: visibleFrame,
            topInset: topInset,
            compactSize: compactSize,
            voiceSize: voiceSize
        )

        XCTAssertEqual(voiceFrame.midX, compactFrame.midX)
        XCTAssertEqual(voiceFrame.midY, compactFrame.midY)
        XCTAssertEqual(voiceFrame.size, voiceSize)
    }

    func testPTTExpansionIgnoresTransientFrameWhenDraggingDisabled() {
        let notificationFrame = NSRect(x: 505, y: 738, width: 430, height: 122)

        let voiceFrame = FloatingControlBarGeometry.pushToTalkFrame(
            currentFrame: notificationFrame,
            expanded: true,
            draggable: false,
            visibleFrame: visibleFrame,
            topInset: topInset,
            compactSize: compactSize,
            voiceSize: voiceSize
        )

        XCTAssertEqual(voiceFrame.origin.x, 608)
        XCTAssertEqual(voiceFrame.origin.y, 832)
        XCTAssertEqual(voiceFrame.size, voiceSize)
    }

    func testPTTCollapseSnapsToDefaultWhenDraggingDisabled() {
        let shiftedVoiceFrame = NSRect(x: 612, y: 832, width: voiceSize.width, height: voiceSize.height)

        let collapsedFrame = FloatingControlBarGeometry.pushToTalkFrame(
            currentFrame: shiftedVoiceFrame,
            expanded: false,
            draggable: false,
            visibleFrame: visibleFrame,
            topInset: topInset,
            compactSize: compactSize,
            voiceSize: voiceSize
        )

        XCTAssertEqual(collapsedFrame.origin.x, 700)
        XCTAssertEqual(collapsedFrame.origin.y, 846)
        XCTAssertEqual(collapsedFrame.size, compactSize)
    }

    func testPTTCollapsePreservesUserCenterWhenDraggingEnabled() {
        let shiftedVoiceFrame = NSRect(x: 612, y: 832, width: voiceSize.width, height: voiceSize.height)

        let collapsedFrame = FloatingControlBarGeometry.pushToTalkFrame(
            currentFrame: shiftedVoiceFrame,
            expanded: false,
            draggable: true,
            visibleFrame: visibleFrame,
            topInset: topInset,
            compactSize: compactSize,
            voiceSize: voiceSize
        )

        XCTAssertEqual(collapsedFrame.midX, shiftedVoiceFrame.midX)
        XCTAssertEqual(collapsedFrame.midY, shiftedVoiceFrame.midY)
        XCTAssertEqual(collapsedFrame.size, compactSize)
    }
}
