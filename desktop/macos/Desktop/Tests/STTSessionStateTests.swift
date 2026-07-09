import XCTest
@testable import Omi_Computer

final class STTSessionStateTests: XCTestCase {
  func testResolveMode_defaultAppleSiliconMic_isLocal() {
    var session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    XCTAssertEqual(mode, .local)
  }

  func testResolveMode_bleDevice_isCloud() {
    var session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .bleDevice,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    XCTAssertEqual(mode, .cloud)
  }

  func testResolveMode_intelMac_isCloud() {
    var session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .microphone,
      isAppleSilicon: false,
      debugForceCloud: false
    )
    XCTAssertEqual(mode, .cloud)
  }

  func testResolveMode_debugForceCloud_isCloud() {
    var session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: true
    )
    XCTAssertEqual(mode, .cloud)
  }

  func testLocalModelFailure_setsAppRunCloudSticky_blocksCloudToLocalRetry() {
    var session = STTSessionState()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    XCTAssertTrue(session.canBeginLocalToCloudFallback(isTranscribing: true))
    session.beginLocalToCloudFallback()
    XCTAssertTrue(session.appRunForceCloud)
    XCTAssertTrue(session.fallbackInProgress)

    session.completeFallback()
    session.endRecording()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    XCTAssertEqual(session.activeMode, .cloud)
    XCTAssertFalse(
      session.canBeginCloudToLocalFallback(
        isTranscribing: true,
        audioSource: .microphone,
        isAppleSilicon: true
      )
    )
  }

  func testCloudReconnectFailure_setsSessionLocalSticky_once() {
    var session = STTSessionState()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: true
    )
    XCTAssertEqual(session.activeMode, .cloud)
    XCTAssertTrue(
      session.canBeginCloudToLocalFallback(
        isTranscribing: true,
        audioSource: .microphone,
        isAppleSilicon: true
      )
    )

    session.beginCloudToLocalFallback()
    XCTAssertTrue(session.sessionForceLocal)
    XCTAssertTrue(session.cloudToLocalFallbackTried)
    XCTAssertFalse(
      session.canBeginCloudToLocalFallback(
        isTranscribing: true,
        audioSource: .microphone,
        isAppleSilicon: true
      )
    )

    // Restart while fallback mutex is held — session sticky must survive.
    session.endRecording()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: true
    )
    XCTAssertEqual(session.activeMode, .local)
    session.completeFallback()

    // Fresh user-initiated recording clears session sticky.
    session.endRecording()
    session.prepareForStart()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: true
    )
    XCTAssertEqual(session.activeMode, .cloud)
  }

  func testStartWhileNotFallingBack_resetsSessionFlags_notAppRunSticky() {
    var session = STTSessionState()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    session.beginLocalToCloudFallback()
    session.completeFallback()
    session.endRecording()

    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: true
    )
    session.beginCloudToLocalFallback()
    session.completeFallback()
    session.endRecording()

    XCTAssertTrue(session.appRunForceCloud)
    XCTAssertTrue(session.sessionForceLocal)
    XCTAssertTrue(session.cloudToLocalFallbackTried)

    session.prepareForStart()
    XCTAssertFalse(session.sessionForceLocal)
    XCTAssertFalse(session.cloudToLocalFallbackTried)
    XCTAssertTrue(session.appRunForceCloud)
  }

  func testBeginFallback_setsInProgress_blocksReentry() {
    var session = STTSessionState()
    session.beginRecording(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    session.beginLocalToCloudFallback()
    XCTAssertFalse(session.canBeginLocalToCloudFallback(isTranscribing: true))
    XCTAssertFalse(
      session.canBeginCloudToLocalFallback(
        isTranscribing: true,
        audioSource: .microphone,
        isAppleSilicon: true
      )
    )

    session.prepareForStart()
    XCTAssertTrue(session.fallbackInProgress)
    XCTAssertTrue(session.appRunForceCloud)
  }

  func testDebugForceCloudSTT_combinesEnvironmentAndDefaults() {
    XCTAssertTrue(
      STTSessionState.debugForceCloudSTT(
        environmentForceCloud: true,
        userDefaultsForceCloud: false
      )
    )
    XCTAssertTrue(
      STTSessionState.debugForceCloudSTT(
        environmentForceCloud: false,
        userDefaultsForceCloud: true
      )
    )
    XCTAssertFalse(
      STTSessionState.debugForceCloudSTT(
        environmentForceCloud: false,
        userDefaultsForceCloud: false
      )
    )
  }

  func testLocalToCloudFallback_clearsStaleSessionForceLocal() {
    // When cloud->local fallback set sessionForceLocal, a subsequent
    // local->cloud fallback must clear it so resolveMode honors the cloud path.
    var session = STTSessionState()
    session.beginCloudToLocalFallback()
    XCTAssertTrue(session.sessionForceLocal)

    session.completeFallback()
    session.beginLocalToCloudFallback()
    XCTAssertFalse(session.sessionForceLocal)
    XCTAssertTrue(session.appRunForceCloud)
    XCTAssertTrue(session.fallbackInProgress)
  }
}
