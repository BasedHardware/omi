import AppKit
import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

@MainActor
final class FloatingBarLayoutTests: XCTestCase {
  private let metrics = FloatingBarLayout.Metrics(
    compactSideWidth: 30,
    activeSideWidth: 42,
    voiceSideWidth: 86,
    thinkingSideWidth: 42,
    hiddenCenterWidth: 206,
    chromeHeight: 58,
    expandedWidth: 430,
    hoverMenuHeight: 104,
    minBarSize: NSSize(width: 40, height: 14),
    voiceBarSize: NSSize(width: 224, height: 42)
  )

  func testVoicePhaseKeepsHintDistinctFromCapture() {
    XCTAssertEqual(FloatingBarVoicePhase.from(VoiceTurnUIProjection(isListening: true)), .listening)
    XCTAssertEqual(FloatingBarVoicePhase.from(VoiceTurnUIProjection(hint: "Hold longer")), .hint)
    XCTAssertEqual(FloatingBarVoicePhase.from(VoiceTurnUIProjection(isThinking: true)), .thinking)
    XCTAssertEqual(
      FloatingBarVoicePhase.from(VoiceTurnUIProjection(isResponseActive: true)), .responding)
    XCTAssertEqual(FloatingBarVoicePhase.from(.idle), .idle)
    XCTAssertTrue(FloatingBarVoicePhase.hint.reservesSurface)
    XCTAssertFalse(FloatingBarVoicePhase.hint.isCapturing)
  }

  func testLobeWidthUsesCaptureWidthOnlyWhileListening() {
    XCTAssertEqual(
      FloatingBarLayout.lobeWidth(
        phase: .listening, isChatPresented: false, hasAgentPills: false, metrics: metrics),
      86)
    XCTAssertEqual(
      FloatingBarLayout.lobeWidth(
        phase: .hint, isChatPresented: false, hasAgentPills: false, metrics: metrics),
      42,
      "a failure hint must not reuse the capture waveform lobe")
    XCTAssertEqual(
      FloatingBarLayout.lobeWidth(
        phase: .idle, isChatPresented: false, hasAgentPills: false, metrics: metrics),
      30)
  }

  func testWindowAndViewReadTheSameLobeWidth() {
    let window = FloatingControlBarWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    window.makeKeyAndOrderFront(nil)
    defer { window.close() }

    let layout = window.currentLayout()
    XCTAssertEqual(
      layout.chromeWidth,
      FloatingBarLayout.chromeWidth(
        lobeWidth: layout.lobeWidth, hiddenCenterWidth: window.layoutMetrics().hiddenCenterWidth))
    XCTAssertEqual(
      layout.closedSurface,
      window.closedSurfaceSize(usesNotchIsland: window.state.usesNotchIsland))
  }

  func testANewTransitionInvalidatesThePreviousCompletion() {
    let owner = FloatingBarFrameTransition()
    let first = owner.start(pendingTarget: NSRect(x: 0, y: 0, width: 10, height: 10))
    let second = owner.start(pendingTarget: NSRect(x: 0, y: 0, width: 20, height: 10))
    XCTAssertFalse(owner.isCurrent(first), "a later start must invalidate the previous token")
    XCTAssertTrue(owner.isCurrent(second))
    XCTAssertEqual(owner.pendingTarget?.width, 20)
  }
}
