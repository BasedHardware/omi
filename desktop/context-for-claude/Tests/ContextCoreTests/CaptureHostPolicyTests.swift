import ContextCore
import XCTest

final class CaptureHostPolicyTests: XCTestCase {
    func testAppleSiliconUsesLocalSTTAndThreeSecondScreenInterval() {
        let policy = CaptureHostPolicy(isAppleSilicon: true)
        XCTAssertTrue(policy.usesLocalSTT)
        XCTAssertEqual(policy.screenCaptureInterval, CaptureHostPolicy.appleSiliconScreenInterval)
        XCTAssertEqual(policy.screenCaptureInterval, 3.0)
    }

    func testIntelDisablesLocalSTTAndUsesNineSecondScreenInterval() {
        let policy = CaptureHostPolicy(isAppleSilicon: false)
        XCTAssertFalse(policy.usesLocalSTT)
        XCTAssertEqual(policy.screenCaptureInterval, CaptureHostPolicy.intelScreenInterval)
        XCTAssertEqual(policy.screenCaptureInterval, 9.0)
    }

    func testAudioCaptureDecisionStartsLocalOnlyWhenPolicyAllows() {
        let silicon = AudioCaptureDecision.make(usesLocalSTT: true)
        XCTAssertTrue(silicon.startLocalSTT)
        XCTAssertFalse(silicon.teardownCaptureOnLocalSTTFailure)

        let intel = AudioCaptureDecision.make(usesLocalSTT: false)
        XCTAssertFalse(intel.startLocalSTT)
        XCTAssertFalse(intel.teardownCaptureOnLocalSTTFailure)
    }

    func testLocalSTTFailureNeverStopsCapture() {
        // Engine must keep mic/system + cloud pump alive when Parakeet fails to load.
        XCTAssertFalse(CaptureHostPolicy.localSTTFailureStopsCapture)
        let decision = AudioCaptureDecision.make(usesLocalSTT: true)
        XCTAssertFalse(decision.teardownCaptureOnLocalSTTFailure)
    }

    func testCloudGapReasonNilWhenLocalSTTAvailable() {
        for cloud in CloudTranscriptionState.allCasesForTest {
            XCTAssertNil(
                CaptureHostPolicy.cloudTranscriptionGapReason(
                    usesLocalSTT: true, isSignedIn: false, cloud: cloud),
                "Silicon keeps on-device fallback; cloud gaps are not 'no transcription'")
        }
    }

    func testCloudGapReasonNilWhileLiveOrConnectingOnIntel() {
        XCTAssertNil(
            CaptureHostPolicy.cloudTranscriptionGapReason(
                usesLocalSTT: false, isSignedIn: true, cloud: .live))
        XCTAssertNil(
            CaptureHostPolicy.cloudTranscriptionGapReason(
                usesLocalSTT: false, isSignedIn: true, cloud: .connecting))
    }

    func testResumeMustReapplyTranscriptionGapAfterReasonWipe() {
        // Engine.resume wipes non-storage reasons then restarts cloud transcription. The gap
        // policy must still produce a signed-out Intel reason so that wipe cannot leave a
        // healthy-looking state with no ASR.
        let afterWipe = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: false, cloud: .idle)
        XCTAssertNotNil(afterWipe)
        XCTAssertTrue(afterWipe?.contains("Omi account") == true)
    }

    func testCloudGapReasonSignedOutOnIntel() {
        let reason = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: false, cloud: .idle)
        XCTAssertEqual(
            reason,
            "Transcription needs an Omi account — sign in to keep transcripts on this Mac")
    }

    func testCloudGapReasonOfflineOnIntel() {
        let reason = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: true, cloud: .failed)
        XCTAssertEqual(
            reason,
            "Transcription needs a network connection to Omi — audio is still captured but nothing is being transcribed")
    }

    func testCloudGapReasonPaywalledOnIntel() {
        let reason = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: true, cloud: .paywalled)
        XCTAssertEqual(
            reason,
            "Transcription off — Omi trial expired; upgrade to keep transcripts on this Mac")
    }
}

extension CloudTranscriptionState {
    fileprivate static var allCasesForTest: [CloudTranscriptionState] {
        [.idle, .connecting, .live, .failed, .paywalled]
    }
}
