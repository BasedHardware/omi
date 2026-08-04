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

    // MARK: - Socket → cloud state mapping

    func testResolvedCloudStateSignedInIdleIsConnecting() {
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(socket: .idle, isSignedIn: true),
            .connecting)
    }

    func testResolvedCloudStateSignedOutIdleStaysIdle() {
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(socket: .idle, isSignedIn: false),
            .idle)
    }

    func testResolvedCloudStateReconnectingFailureIsConnecting() {
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(
                socket: .failed("Socket closed — reconnecting"),
                isSignedIn: true),
            .connecting)
    }

    func testResolvedCloudStatePermanentFailureStaysFailed() {
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(
                socket: .failed("Unauthorized"),
                isSignedIn: true),
            .failed)
    }

    func testResolvedCloudStatePassthroughCases() {
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(socket: .connecting, isSignedIn: false),
            .connecting)
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(socket: .live, isSignedIn: false),
            .live)
        XCTAssertEqual(
            CaptureHostPolicy.resolvedCloudTranscriptionState(socket: .paywalled, isSignedIn: true),
            .paywalled)
    }

    // MARK: - Outbound PCM while connecting

    func testIdleWithWantsConnectionBuffersPCM() {
        // The Intel bug: mixer can emit before connect() flips idle → connecting.
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .idle, wantsConnection: true, hasLiveTask: false),
            .buffer)
    }

    func testIdleWithoutWantsConnectionDropsPCM() {
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .idle, wantsConnection: false, hasLiveTask: false),
            .drop)
    }

    func testPaywalledAndAirgappedAlwaysDropPCM() {
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .paywalled, wantsConnection: true, hasLiveTask: false),
            .drop)
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .airgapped, wantsConnection: true, hasLiveTask: false),
            .drop)
    }

    func testCloudGapReasonAirgappedOnIntel() {
        let reason = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: true, cloud: .airgapped)
        XCTAssertEqual(
            reason,
            "Transcription off — Airgap Mode is on; turn it off to send audio to Omi")
    }

    func testConnectingBuffersAndLiveTransmitsWhenTaskExists() {
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .connecting, wantsConnection: true, hasLiveTask: false),
            .buffer)
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .live, wantsConnection: true, hasLiveTask: true),
            .transmit)
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .live, wantsConnection: true, hasLiveTask: false),
            .buffer)
    }

    func testFailedBuffersOnlyWhileWantingConnection() {
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .failed, wantsConnection: true, hasLiveTask: false),
            .buffer)
        XCTAssertEqual(
            CaptureHostPolicy.outboundPCMAction(
                phase: .failed, wantsConnection: false, hasLiveTask: false),
            .drop)
    }

    // MARK: - Resume wipe ordering

    func testResumeWipeThenGapRefreshPreservesIntelTranscriptionGap() {
        // Correct Engine.resume order: wipe non-storage reasons, then refresh gap from cloud.
        var reasons = [
            "transcription": "stale from previous session",
            "microphone": "denied",
            "storage": "disk full",
        ]
        reasons = CaptureHostPolicy.reasonsAfterResumeWipe(reasons, storageKey: "storage")
        XCTAssertEqual(reasons, ["storage": "disk full"])

        let gap = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: false, cloud: .idle)
        XCTAssertNotNil(gap)
        if let gap {
            reasons["transcription"] = gap
        }
        XCTAssertEqual(reasons["transcription"], gap)
        XCTAssertEqual(reasons["storage"], "disk full")
    }

    func testResumeGapRefreshThenWipeLosesIntelTranscriptionGap() {
        // Documents the historical bug: refreshTranscriptionGap before wipe erased the Intel gap.
        guard let gap = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: false, isSignedIn: false, cloud: .idle)
        else {
            return XCTFail("signed-out Intel idle must produce a gap reason")
        }
        var reasons = ["transcription": gap, "storage": "disk full"]
        // Wrong order: wipe after refresh
        reasons = CaptureHostPolicy.reasonsAfterResumeWipe(reasons, storageKey: "storage")
        XCTAssertNil(
            reasons["transcription"],
            "wipe-after-refresh drops the gap — Engine must wipe first")
        XCTAssertEqual(reasons["storage"], "disk full")
    }
}

extension CloudTranscriptionState {
    fileprivate static var allCasesForTest: [CloudTranscriptionState] {
        [.idle, .connecting, .live, .failed, .paywalled, .airgapped]
    }
}
