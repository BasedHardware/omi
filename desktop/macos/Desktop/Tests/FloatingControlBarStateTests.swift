import XCTest
@testable import Omi_Computer

@MainActor
final class FloatingControlBarStateTests: XCTestCase {
    func testAgentSurfaceDoesNotDependOnMainChatContentOrHeight() {
        let state = FloatingControlBarState()
        let agentID = UUID()

        state.present(.agent(agentID))

        XCTAssertTrue(state.hasVisibleConversation)
        XCTAssertTrue(state.showingAIConversation)
        XCTAssertTrue(state.showingAIResponse)
        XCTAssertEqual(state.activeAgentChatPillID, agentID)
        XCTAssertEqual(state.conversationSurface, .agent(agentID))

        state.reportContentHeight(120, for: .mainResponse)
        XCTAssertNil(state.measuredContentHeight(for: .agent(agentID)))

        state.reportContentHeight(240, for: .agent(agentID))
        XCTAssertEqual(state.measuredContentHeight(for: .agent(agentID)), 240)

        state.leaveAgentSurface()
        XCTAssertNil(state.activeAgentChatPillID)
        XCTAssertEqual(state.conversationSurface, .mainInput)
        XCTAssertTrue(state.showingAIConversation)
        XCTAssertFalse(state.showingAIResponse)
    }

    func testVoiceResponseGlowClearsIfNoOwnerTurnsItOff() {
        let originalDelay = FloatingControlBarState.voiceResponseWatchdogDelay
        FloatingControlBarState.voiceResponseWatchdogDelay = 0.02
        defer { FloatingControlBarState.voiceResponseWatchdogDelay = originalDelay }

        let state = FloatingControlBarState()
        state.isVoiceResponseActive = true

        let expectation = expectation(description: "voice response watchdog fired")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            expectation.fulfill()
        }
        wait(for: [expectation], timeout: 0.2)

        XCTAssertFalse(state.isVoiceResponseActive)
    }

    func testVoiceResponseGlowWatchdogIsCancelledWhenClearedExplicitly() {
        let originalDelay = FloatingControlBarState.voiceResponseWatchdogDelay
        FloatingControlBarState.voiceResponseWatchdogDelay = 0.02
        defer { FloatingControlBarState.voiceResponseWatchdogDelay = originalDelay }

        let state = FloatingControlBarState()
        state.isVoiceResponseActive = true
        state.isVoiceResponseActive = false

        let expectation = expectation(description: "cancelled watchdog would have fired")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            expectation.fulfill()
        }
        wait(for: [expectation], timeout: 0.2)

        XCTAssertFalse(state.isVoiceResponseActive)
    }
}
