import Combine
import XCTest
@testable import Omi_Computer

@MainActor
final class FloatingControlBarStateTests: XCTestCase {
    func testNotchHoverMenuVisibilityIsSingleGatedState() {
        let state = FloatingControlBarState()
        state.usesNotchIsland = true

        state.setNotchHoverMenuOpen(true)
        XCTAssertTrue(state.isNotchHoverMenuVisible)
        XCTAssertTrue(state.isHoveringBar)

        state.showingAIConversation = true
        XCTAssertFalse(state.isNotchHoverMenuVisible)

        state.showingAIConversation = false
        state.isVoiceListening = true
        XCTAssertFalse(state.isNotchHoverMenuVisible)

        state.isVoiceListening = false
        state.setNotchHoverMenuOpen(false)
        XCTAssertFalse(state.isNotchHoverMenuVisible)
        XCTAssertFalse(state.isHoveringBar)
    }

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

    func testContentHeightReportsOnlyMeaningfulChanges() {
        let state = FloatingControlBarState()
        state.present(.mainResponse)

        var publishCount = 0
        let cancellable = state.$responseContentHeights.dropFirst().sink { _ in
            publishCount += 1
        }

        state.reportContentHeight(120.1, for: .mainResponse)
        XCTAssertEqual(state.measuredContentHeight(for: .mainResponse), 120.5)
        XCTAssertEqual(state.responseContentHeight, 120.5)
        XCTAssertEqual(publishCount, 1)

        state.reportContentHeight(120.2, for: .mainResponse)
        XCTAssertEqual(state.measuredContentHeight(for: .mainResponse), 120.5)
        XCTAssertEqual(publishCount, 1)

        state.reportContentHeight(121.0, for: .mainResponse)
        XCTAssertEqual(state.measuredContentHeight(for: .mainResponse), 121)
        XCTAssertEqual(publishCount, 2)

        cancellable.cancel()
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

    // MARK: - Review feedback P2 fixes

    /// Thread 1: After leaving an agent surface and clearing, the surface must be
    /// fully closed (not stale .agent(id)) so canRestoreVisibleConversation returns false.
    func testLeaveAgentSurfaceThenClearDoesNotRestoreStaleAgent() {
        let state = FloatingControlBarState()
        let agentID = UUID()
        state.present(.agent(agentID))
        state.markConversationActivity()

        // Simulate closeAIConversation clearing the surface
        state.activeAgentChatPillID = nil
        state.conversationSurface = .closed
        state.showingAIConversation = false
        state.showingAIResponse = false

        // Stale .agent surface must not trigger a restore
        XCTAssertFalse(state.canRestoreVisibleConversation,
                       "Stale agent surface should not be restorable after close")
        XCTAssertFalse(state.hasVisibleConversation,
                       "hasVisibleConversation should be false after full clear")
    }

    /// Thread 3: leaveAgentSurface lands on .mainInput when there is no main conversation.
    func testLeaveAgentSurfaceLandsOnMainInputWhenNoMainConversation() {
        let state = FloatingControlBarState()
        let agentID = UUID()
        state.present(.agent(agentID))

        state.leaveAgentSurface()

        XCTAssertEqual(state.conversationSurface, .mainInput,
                       "Backing out of a lone agent should land on .mainInput")
        XCTAssertNil(state.activeAgentChatPillID)
        XCTAssertTrue(state.showingAIConversation)
        XCTAssertFalse(state.showingAIResponse)
    }

    /// Thread 3: leaveAgentSurface lands on .mainResponse when there IS a main conversation.
    func testLeaveAgentSurfaceLandsOnMainResponseWhenMainConversationExists() {
        let state = FloatingControlBarState()
        // Seed a main conversation
        state.displayedQuery = "What is the weather?"
        state.currentAIMessage = ChatMessage(text: "Sunny.", sender: .ai)

        let agentID = UUID()
        state.present(.agent(agentID))

        state.leaveAgentSurface()

        XCTAssertEqual(state.conversationSurface, .mainResponse,
                       "Backing out with a main conversation should land on .mainResponse")
        XCTAssertNil(state.activeAgentChatPillID)
        XCTAssertTrue(state.showingAIResponse)
    }

    /// Thread 2: isAgentSwitcherExpanded reflects pinned and hovering states.
    func testIsAgentSwitcherExpanded() {
        let state = FloatingControlBarState()

        XCTAssertFalse(state.isAgentSwitcherExpanded)

        state.agentSwitcherHovering = true
        XCTAssertTrue(state.isAgentSwitcherExpanded)

        state.agentSwitcherHovering = false
        XCTAssertFalse(state.isAgentSwitcherExpanded)

        state.agentSwitcherPinned = true
        XCTAssertTrue(state.isAgentSwitcherExpanded)

        state.agentSwitcherHovering = true
        XCTAssertTrue(state.isAgentSwitcherExpanded)
    }

    /// Thread 3 (Cubic P2): hideConversationSurface() must fully reset all
    /// presentation and process flags so UI state and in-flight workflows
    /// don't desync after the Back button hides the conversation.
    func testHideConversationSurfaceResetsAllState() {
        let state = FloatingControlBarState()
        let agentID = UUID()
        state.present(.agent(agentID))
        state.isAILoading = true
        state.isVoiceFollowUp = true
        state.voiceFollowUpTranscript = "partial transcript"

        // hideConversationSurface() now cancels in-flight work via singletons
        // (cancelChat / cancelListening) before clearing flags. The singletons
        // are safe to call when no actual generation/PTT session is active.
        state.hideConversationSurface()

        XCTAssertNil(state.activeAgentChatPillID)
        XCTAssertEqual(state.conversationSurface, .closed)
        XCTAssertFalse(state.showingAIConversation)
        XCTAssertFalse(state.showingAIResponse)
        XCTAssertFalse(state.isAILoading)
        XCTAssertFalse(state.isVoiceFollowUp)
        XCTAssertEqual(state.voiceFollowUpTranscript, "")
        XCTAssertFalse(state.hasVisibleConversation)
    }
}
