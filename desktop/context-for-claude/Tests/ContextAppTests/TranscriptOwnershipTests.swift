import XCTest

@testable import ContextApp

final class TranscriptOwnershipTests: XCTestCase {
    func testLocalParakeetIsNotFed() {
        XCTAssertFalse(
            TranscriptOwnership.shouldFeedLocal(),
            "backend /v4/listen owns speech; local Parakeet must not receive audio")
    }

    func testPaywalledListenSurfacesASpeechReason() {
        let reason = ListenSpeechStatus.reason(
            state: .paywalled,
            paywall: .freemiumExhausted,
            signedIn: true,
            isPaused: false)
        XCTAssertEqual(
            reason,
            "Speech off — monthly transcription limit reached. Capture resumes next month.")
    }

    func testTrialPaywallHasDistinctCopy() {
        let reason = ListenSpeechStatus.reason(
            state: .paywalled,
            paywall: .trialExpired,
            signedIn: true,
            isPaused: false)
        XCTAssertEqual(
            reason,
            "Speech off — desktop trial ended. Upgrade to keep transcribing.")
    }

    func testPermanentListenFailureSurfacesTheSocketMessage() {
        let reason = ListenSpeechStatus.reason(
            state: .failed("Sign in to Omi again to keep transcribing."),
            paywall: nil,
            signedIn: true,
            isPaused: false)
        XCTAssertEqual(reason, "Sign in to Omi again to keep transcribing.")
    }

    func testSignedOutIdleAsksForSignIn() {
        let reason = ListenSpeechStatus.reason(
            state: .idle, paywall: nil, signedIn: false, isPaused: false)
        XCTAssertEqual(reason, "Sign in to Omi to transcribe speech")
    }

    func testHealthyListenClearsTheSpeechReason() {
        XCTAssertNil(
            ListenSpeechStatus.reason(state: .live, paywall: nil, signedIn: true, isPaused: false))
        XCTAssertNil(
            ListenSpeechStatus.reason(
                state: .connecting, paywall: nil, signedIn: true, isPaused: false))
        XCTAssertNil(
            ListenSpeechStatus.reason(state: .idle, paywall: nil, signedIn: true, isPaused: false))
    }

    func testPausedCaptureStillSurfacesStickyPaywall() {
        // Pause/Resume must not hide the freemium latch — that was the Resume STT bypass.
        XCTAssertEqual(
            ListenSpeechStatus.reason(
                state: .idle, paywall: .freemiumExhausted, signedIn: true, isPaused: true),
            "Speech off — monthly transcription limit reached. Capture resumes next month.")
        XCTAssertEqual(
            ListenSpeechStatus.reason(
                state: .paywalled, paywall: .trialExpired, signedIn: true, isPaused: true),
            "Speech off — desktop trial ended. Upgrade to keep transcribing.")
    }

    func testPausedCaptureHidesNonPaywallListenReasons() {
        XCTAssertNil(
            ListenSpeechStatus.reason(
                state: .failed("network blip"), paywall: nil, signedIn: true, isPaused: true))
    }

    func testSharedUploadClientSessionIdPrefersEngineIdentity() {
        let shared = "11111111-2222-3333-4444-555555555555"
        XCTAssertEqual(
            CaptureSessionIdentity.clientSessionId(
                deviceIdHash: "abcd",
                sessionId: 7,
                sessionStartedAt: 1_700_000_000,
                part: 1,
                sharedClientSessionId: shared),
            shared)
        XCTAssertEqual(
            CaptureSessionIdentity.clientSessionId(
                deviceIdHash: "abcd",
                sessionId: 7,
                sessionStartedAt: 1_700_000_000,
                part: 2,
                sharedClientSessionId: shared),
            "\(shared)-2")
    }
}
