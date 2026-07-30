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
            state: .paywalled, signedIn: true, isPaused: false)
        XCTAssertEqual(
            reason,
            "Speech off — Omi trial expired. Upgrade to keep transcribing.")
    }

    func testPermanentListenFailureSurfacesTheSocketMessage() {
        let reason = ListenSpeechStatus.reason(
            state: .failed("Sign in to Omi again to keep transcribing."),
            signedIn: true,
            isPaused: false)
        XCTAssertEqual(reason, "Sign in to Omi again to keep transcribing.")
    }

    func testSignedOutIdleAsksForSignIn() {
        let reason = ListenSpeechStatus.reason(
            state: .idle, signedIn: false, isPaused: false)
        XCTAssertEqual(reason, "Sign in to Omi to transcribe speech")
    }

    func testHealthyListenClearsTheSpeechReason() {
        XCTAssertNil(ListenSpeechStatus.reason(state: .live, signedIn: true, isPaused: false))
        XCTAssertNil(ListenSpeechStatus.reason(state: .connecting, signedIn: true, isPaused: false))
        XCTAssertNil(ListenSpeechStatus.reason(state: .idle, signedIn: true, isPaused: false))
    }

    func testPausedCaptureHidesListenReasons() {
        XCTAssertNil(
            ListenSpeechStatus.reason(state: .paywalled, signedIn: true, isPaused: true))
    }
}
