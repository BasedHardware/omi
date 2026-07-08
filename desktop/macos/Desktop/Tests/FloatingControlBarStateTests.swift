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
        // Seed a main conversation via viewport anchors / optimistic query
        state.displayedQuery = "What is the weather?"
        state.bindAnswerMessage(ChatMessage(text: "Sunny.", sender: .ai))

        let agentID = UUID()
        state.present(.agent(agentID))

        state.leaveAgentSurface()

        XCTAssertEqual(state.conversationSurface, .mainResponse,
                       "Backing out with a main conversation should land on .mainResponse")
        XCTAssertNil(state.activeAgentChatPillID)
        XCTAssertTrue(state.showingAIResponse)
    }

    /// Phase 3: floating bar derives answer/history from provider messages by viewport ids.
    func testViewportDerivesCurrentAnswerAndHistoryFromProviderMessages() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()

        let question = ChatMessage(id: "q1", clientTurnId: "turn-1", text: "Hello?", sender: .user, isSynced: true)
        let answer = ChatMessage(id: "a1", clientTurnId: "turn-1", text: "Hi there.", sender: .ai, isSynced: true)
        let followUpQ = ChatMessage(id: "q2", clientTurnId: "turn-2", text: "More?", sender: .user, isSynced: true)
        let followUpA = ChatMessage(id: "a2", clientTurnId: "turn-2", text: "Sure.", sender: .ai, isSynced: true)
        provider.messages = [question, answer, followUpQ, followUpA]

        state.bindQuestionMessageId("q1")
        state.bindAnswerMessage(answer)
        state.archiveCurrentExchange(using: provider)
        state.displayedQuery = "More?"
        state.beginTurn(clientTurnId: "turn-2")
        state.bindQuestionMessageId("q2")
        state.bindAnswerMessage(followUpA)

        let current = state.currentAIMessage(from: provider)
        XCTAssertEqual(current?.id, "a2")
        XCTAssertEqual(current?.text, "Sure.")

        let history = state.derivedChatHistory(from: provider)
        XCTAssertEqual(history.count, 1)
        XCTAssertEqual(history[0].questionMessageId, "q1")
        XCTAssertEqual(history[0].aiMessage.id, "a1")
        XCTAssertEqual(history[0].question, "Hello?")

        let shareIds = state.syncedShareMessageIds(from: provider)
        XCTAssertEqual(shareIds, ["q1", "a1", "q2", "a2"])

        // Mutating provider message text is reflected without copying into state.
        provider.messages[3].text = "Sure — updated."
        XCTAssertEqual(state.currentAIMessage(from: provider)?.text, "Sure — updated.")
    }

    /// Close/restore uses activity + viewport anchors, not copied transcript text.
    func testCanRestoreUsesViewportAnchorsAndActivityWindow() {
        let state = FloatingControlBarState()
        XCTAssertFalse(state.canRestoreVisibleConversation)

        state.displayedQuery = "pending"
        state.markConversationActivity(at: Date())
        XCTAssertTrue(state.canRestoreVisibleConversation)

        state.clearVisibleConversation(cancelInFlightWork: false)
        XCTAssertFalse(state.canRestoreVisibleConversation)
        XCTAssertFalse(state.chatViewport.hasAnchors)
        XCTAssertTrue(state.displayedQuery.isEmpty)
    }

    /// Bind answer + archived exchanges; restore stays valid within the activity
    /// window, and clearVisibleConversation wipes all viewport anchors.
    func testBindAnswerAndArchivedExchangesRestoreThenClearWipesAnchors() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()
        let question = ChatMessage(id: "q1", clientTurnId: "turn-1", text: "Hi?", sender: .user)
        let answer = ChatMessage(id: "a1", clientTurnId: "turn-1", text: "Hello.", sender: .ai)
        let followUp = ChatMessage(id: "a2", clientTurnId: "turn-2", text: "More.", sender: .ai)
        provider.messages = [question, answer, followUp]

        state.bindQuestionMessageId("q1")
        state.bindAnswerMessage(answer)
        state.archiveCurrentExchange(using: provider)
        state.bindAnswerMessage(followUp)
        state.markConversationActivity(at: Date())
        state.present(.mainResponse)

        XCTAssertTrue(state.chatViewport.hasAnchors)
        XCTAssertEqual(state.chatViewport.archivedExchanges.count, 1)
        XCTAssertEqual(state.chatViewport.answerMessageId, "a2")
        XCTAssertTrue(state.canRestoreVisibleConversation)

        state.clearVisibleConversation(cancelInFlightWork: false)
        XCTAssertFalse(state.chatViewport.hasAnchors)
        XCTAssertTrue(state.chatViewport.archivedExchanges.isEmpty)
        XCTAssertNil(state.chatViewport.answerMessageId)
        XCTAssertNil(state.lastConversationActivityAt)
        XCTAssertFalse(state.canRestoreVisibleConversation)
    }

    /// Closing mid-stream keeps viewport anchors + activity so restore works;
    /// clear then makes restore impossible.
    func testCloseMidStreamKeepsAnchorsRestorableUntilClear() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()
        let answer = ChatMessage(
            id: "a-stream",
            clientTurnId: "turn-stream",
            text: "Partial…",
            sender: .ai,
            isStreaming: true
        )
        provider.messages = [answer]

        state.beginTurn(clientTurnId: "turn-stream")
        state.bindAnswerMessage(answer)
        state.present(.mainResponse)
        state.isAILoading = true
        state.markConversationActivity(at: Date())

        // Simulate closeAIConversation: hide surface but keep viewport anchors.
        state.hideConversationSurface()

        XCTAssertEqual(state.chatViewport.answerMessageId, "a-stream")
        XCTAssertTrue(state.chatViewport.hasAnchors)
        XCTAssertNotNil(state.lastConversationActivityAt)
        XCTAssertTrue(state.canRestoreVisibleConversation)

        state.clearVisibleConversation(cancelInFlightWork: false)
        XCTAssertFalse(state.canRestoreVisibleConversation)
        XCTAssertNil(state.chatViewport.answerMessageId)
        XCTAssertFalse(state.chatViewport.hasAnchors)
    }

    /// currentAIMessage prefers the provider message when override is nil and id is bound.
    func testCurrentAIMessagePrefersProviderWhenOverrideNilAndIdBound() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()
        let answer = ChatMessage(id: "a1", clientTurnId: "t1", text: "From provider", sender: .ai)
        provider.messages = [answer]

        state.bindAnswerMessage(answer)
        XCTAssertNil(state.localAnswerOverride)
        XCTAssertEqual(state.currentAIMessage(from: provider)?.text, "From provider")

        provider.messages[0].text = "Updated in provider"
        XCTAssertEqual(state.currentAIMessage(from: provider)?.text, "Updated in provider")
    }

    /// Ephemeral override (no answer id) is returned; when both are somehow set,
    /// a bound answerMessageId wins (provider SoT).
    func testCurrentAIMessageEphemeralOverrideVsProviderBoundWins() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()
        let answer = ChatMessage(id: "a1", clientTurnId: "t1", text: "Provider answer", sender: .ai)
        provider.messages = [answer]
        let ephemeral = ChatMessage(text: "Usage limit reached", sender: .ai)

        state.setLocalAnswerOverride(ephemeral)
        XCTAssertNil(state.chatViewport.answerMessageId)
        XCTAssertEqual(state.currentAIMessage(from: provider)?.text, "Usage limit reached")

        // Force both set (should not happen via normal APIs after bind).
        var viewport = state.chatViewport
        viewport.answerMessageId = answer.id
        state.chatViewport = viewport
        XCTAssertNotNil(state.localAnswerOverride)
        XCTAssertEqual(
            state.currentAIMessage(from: provider)?.text,
            "Provider answer",
            "Bound answerMessageId must win over localAnswerOverride"
        )
    }

    /// Block-only answers (empty text, non-empty contentBlocks) are not empty failures.
    func testBlockOnlyAnswerIsNotEmptyResponseFailure() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()
        let blockOnly = ChatMessage(
            id: "a-blocks",
            clientTurnId: "turn-blocks",
            text: "",
            sender: .ai,
            contentBlocks: [.text(id: "b1", text: "Structured only")]
        )
        provider.messages = [blockOnly]

        XCTAssertTrue(FloatingControlBarState.messageHasAnswerContent(blockOnly))
        state.bindAnswerMessage(blockOnly)
        XCTAssertTrue(state.hasProviderBackedAnswerContent(from: provider))
        XCTAssertFalse(
            state.shouldPresentEmptyResponseFailure(from: provider),
            "Bound provider answer with contentBlocks must not be treated as failed empty"
        )
        XCTAssertTrue(state.aiResponseText(from: provider).isEmpty)

        // Truly empty: no message at all.
        let emptyState = FloatingControlBarState()
        XCTAssertTrue(emptyState.shouldPresentEmptyResponseFailure(from: provider))

        // Unbound empty-text message with no blocks/resources is a failure.
        let emptyText = ChatMessage(id: "a-empty", text: "", sender: .ai)
        provider.messages = [emptyText]
        emptyState.beginTurn(clientTurnId: "t-empty")
        // Resolve via activeClientTurnId without binding answer id.
        var viewport = emptyState.chatViewport
        viewport.activeClientTurnId = "t-empty"
        emptyState.chatViewport = viewport
        let emptyTurnMessage = ChatMessage(
            id: "a-empty-turn",
            clientTurnId: "t-empty",
            text: "",
            sender: .ai
        )
        provider.messages = [emptyTurnMessage]
        XCTAssertTrue(emptyState.shouldPresentEmptyResponseFailure(from: provider))
    }

    /// Resource-only answers also count as provider-backed content.
    func testResourceOnlyAnswerIsNotEmptyResponseFailure() {
        let state = FloatingControlBarState()
        let provider = ChatProvider()
        let resource = ChatResource.localGeneratedFile(
            id: "res-1",
            title: "out.txt",
            subtitle: "text/plain",
            mimeType: "text/plain",
            uri: "file:///tmp/out.txt"
        )
        let resourceOnly = ChatMessage(
            id: "a-res",
            clientTurnId: "turn-res",
            text: "",
            sender: .ai,
            resources: [resource]
        )
        provider.messages = [resourceOnly]
        state.bindAnswerMessage(resourceOnly)
        XCTAssertFalse(state.shouldPresentEmptyResponseFailure(from: provider))
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
