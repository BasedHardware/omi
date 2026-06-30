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

    func testNotchChromeActivationIgnoresTransparentBottomOutset() {
        let windowFrame = NSRect(x: 500, y: 800, width: 360, height: 58)

        XCTAssertTrue(FloatingControlBarGeometry.notchChromeActivationContains(
            mouseLocation: NSPoint(x: 680, y: 850),
            windowFrame: windowFrame,
            chromeHeight: 17,
            horizontalOutset: 24
        ))
        XCTAssertFalse(FloatingControlBarGeometry.notchChromeActivationContains(
            mouseLocation: NSPoint(x: 680, y: 838),
            windowFrame: windowFrame,
            chromeHeight: 17,
            horizontalOutset: 24
        ))
    }

    func testNotchChromeActivationLocalIgnoresTransparentBottomOutset() {
        let windowSize = NSSize(width: 360, height: 58)

        XCTAssertTrue(FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: NSPoint(x: 180, y: 50),
            windowSize: windowSize,
            chromeHeight: 17,
            horizontalOutset: 24
        ))
        XCTAssertFalse(FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: NSPoint(x: 180, y: 40),
            windowSize: windowSize,
            chromeHeight: 17,
            horizontalOutset: 24
        ))
    }

    func testNotchOpenMenuRetentionIncludesRowsButNotBottomGlow() {
        let windowSize = NSSize(width: 430, height: FloatingControlBarWindow.notchChromeHeight + 96 + 24)
        let visibleSurfaceHeight: CGFloat = FloatingControlBarWindow.notchChromeHeight + 96

        XCTAssertTrue(FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: NSPoint(x: 215, y: windowSize.height - visibleSurfaceHeight + 6),
            windowSize: windowSize,
            chromeHeight: visibleSurfaceHeight,
            horizontalOutset: 24
        ))
        XCTAssertFalse(FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: NSPoint(x: 215, y: 8),
            windowSize: windowSize,
            chromeHeight: visibleSurfaceHeight,
            horizontalOutset: 24
        ))
    }

    func testNotchHoverMenuKeepsBottomMarginWithoutSubagents() {
        XCTAssertEqual(
            FloatingControlBarWindow.notchHoverMenuHeight(agentCount: 0),
            FloatingControlBarWindow.notchAgentListRowHeight + FloatingControlBarWindow.notchHoverMenuBottomMargin
        )
    }

    func testNotchChromeHeightUsesMeasuredAuxiliaryAreaHeight() {
        let height = FloatingControlBarWindow.notchChromeHeight(
            topSafeAreaInset: 30,
            auxiliaryTopLeftArea: NSRect(x: 0, y: 860, width: 600, height: 48),
            auxiliaryTopRightArea: NSRect(x: 840, y: 860, width: 600, height: 48)
        )

        XCTAssertEqual(height, 48)
    }

    func testNotchChromeHeightFallsBackToSafeAreaInset() {
        let height = FloatingControlBarWindow.notchChromeHeight(
            topSafeAreaInset: 44,
            auxiliaryTopLeftArea: nil,
            auxiliaryTopRightArea: nil
        )

        XCTAssertEqual(height, 44)
    }

    func testNotchChromeHeightKeepsDefaultForLegacyDisplays() {
        let height = FloatingControlBarWindow.notchChromeHeight(
            topSafeAreaInset: 0,
            auxiliaryTopLeftArea: nil,
            auxiliaryTopRightArea: nil
        )

        XCTAssertEqual(height, FloatingControlBarWindow.notchChromeHeight)
    }

    func testMeasuredNotchChromeHeightAcceptsFullVisibleChromeButNotGlow() {
        let measuredChromeHeight = FloatingControlBarWindow.notchChromeHeight(
            topSafeAreaInset: 48,
            auxiliaryTopLeftArea: nil,
            auxiliaryTopRightArea: nil
        )
        let windowSize = NSSize(width: 360, height: measuredChromeHeight + FloatingControlBarWindow.notchGlowOutsetBottom)

        XCTAssertTrue(FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: NSPoint(x: 180, y: FloatingControlBarWindow.notchGlowOutsetBottom + 2),
            windowSize: windowSize,
            chromeHeight: measuredChromeHeight,
            horizontalOutset: FloatingControlBarWindow.notchGlowOutsetX
        ))
        XCTAssertFalse(FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: NSPoint(x: 180, y: FloatingControlBarWindow.notchGlowOutsetBottom - 2),
            windowSize: windowSize,
            chromeHeight: measuredChromeHeight,
            horizontalOutset: FloatingControlBarWindow.notchGlowOutsetX
        ))
    }

    func testNotchChromeActivationIgnoresHorizontalGlowOutsets() {
        let windowFrame = NSRect(x: 500, y: 800, width: 360, height: 58)

        XCTAssertFalse(FloatingControlBarGeometry.notchChromeActivationContains(
            mouseLocation: NSPoint(x: 512, y: 850),
            windowFrame: windowFrame,
            chromeHeight: 17,
            horizontalOutset: 24
        ))
        XCTAssertFalse(FloatingControlBarGeometry.notchChromeActivationContains(
            mouseLocation: NSPoint(x: 848, y: 850),
            windowFrame: windowFrame,
            chromeHeight: 17,
            horizontalOutset: 24
        ))
    }
}
