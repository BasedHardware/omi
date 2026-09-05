import XCTest

@testable import Omi_Computer

final class STTSessionStateTests: XCTestCase {
  func testResolveMode_defaultAppleSiliconMic_isLocal() {
    let session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .microphone,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    XCTAssertEqual(mode, .local)
  }

  func testResolveMode_bleDevice_isCloud() {
    let session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .bleDevice,
      isAppleSilicon: true,
      debugForceCloud: false
    )
    XCTAssertEqual(mode, .cloud)
  }

  func testResolveMode_intelMac_isCloud() {
    let session = STTSessionState()
    let mode = session.resolveMode(
      audioSource: .microphone,
      isAppleSilicon: false,
      debugForceCloud: false
    )
    XCTAssertEqual(mode, .cloud)
  }

  func testResolveMode_debugForceCloud_isCloud() {
    let session = STTSessionState()
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

  // MARK: - Wake word needs a recognizer that can be told its name

  /// Ambient transcription is on-device by default on Apple Silicon, and the on-device
  /// recognizer takes a language hint and nothing else — no keyword or vocabulary
  /// parameter — so it cannot be told that "Omi" is a word. The cloud lane reaches
  /// `/v4/listen`, which prepends "Omi" to the STT keyword vocabulary server-side
  /// (`backend/utils/listen_session_bootstrap.py`). Measured on one machine, same script
  /// and voices, only the lane changed: usable in 12 of 20 utterances on-device against
  /// 19 of 20 on the cloud lane. Seven of the eight on-device misses came back as "Only",
  /// which cannot be accepted as a rendering because it opens ordinary sentences.
  func testWakeWordOptInResolvesToCloudOnAppleSilicon() {
    let state = STTSessionState()
    XCTAssertEqual(
      state.resolveMode(
        audioSource: .microphone, isAppleSilicon: true, debugForceCloud: false,
        wakeWordNeedsRecognizableName: true),
      .cloud)
  }

  /// Default-config users keep on-device transcription exactly as today. The opt-in is a
  /// privacy and cost decision, so nothing changes until it is made.
  func testWithoutTheOptInAppleSiliconStaysOnDevice() {
    let state = STTSessionState()
    XCTAssertEqual(
      state.resolveMode(
        audioSource: .microphone, isAppleSilicon: true, debugForceCloud: false,
        wakeWordNeedsRecognizableName: false),
      .local)
  }

  /// A session that already fell back to on-device after cloud reconnect exhaustion stays
  /// there; the opt-in must not drag a failing session back onto the lane it just left.
  func testSessionForcedLocalIsNotDraggedBackToCloud() {
    var state = STTSessionState()
    state.beginCloudToLocalFallback()
    XCTAssertEqual(
      state.resolveMode(
        audioSource: .microphone, isAppleSilicon: true, debugForceCloud: false,
        wakeWordNeedsRecognizableName: true),
      .local)
  }

  /// The pendant already transcribes in the cloud, so the opt-in changes nothing there.
  func testBleDeviceIsUnaffected() {
    let state = STTSessionState()
    XCTAssertEqual(
      state.resolveMode(
        audioSource: .bleDevice, isAppleSilicon: true, debugForceCloud: false,
        wakeWordNeedsRecognizableName: false),
      .cloud)
  }
}
