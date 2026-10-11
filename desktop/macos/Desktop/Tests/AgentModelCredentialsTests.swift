import XCTest

@testable import Omi_Computer

@MainActor
final class AgentModelCredentialsTests: XCTestCase {
  func testOwnerReplacementDropsCredentialReply() async {
    var current = true
    let result = await AgentModelCredentials.resolve(
      isCurrent: { current },
      fetch: {
        current = false
        return ["Authorization": "Bearer inert-test-only"]
      })
    XCTAssertNil(result.headers)
    XCTAssertEqual(result.failureCode, "authentication")
  }

  func testBareManaged401IsTypedSessionFailureWithSignInRecovery() {
    let failure = AgentRuntimeFailure(
      code: "omi_session_authentication", failureCode: .authentication,
      userMessage: "Your session expired. Sign in to continue.",
      technicalMessage: "HTTP 401 status code (no body)", adapterId: "pi-mono", provider: "omi", retryable: false)
    let error = BridgeError.agentRuntimeFailure(failure)
    XCTAssertTrue(error.isSessionAuthenticationFailure)
    XCTAssertEqual(ChatErrorState.from(error), .authRequired)
    XCTAssertEqual(ChatErrorState.from(error)?.primaryRecovery, .signIn)
    let notice = ChatTurnFailureNotice.forTurn(
      error: error, watchdogFired: false, toolStallAbortFired: false,
      timeoutMessage: nil, providerAuthMessage: "Provider sign-in")
    XCTAssertEqual(notice?.text, "Your session expired. Sign in to continue.")
    XCTAssertEqual(notice?.retryable, false)
  }

  func testTypedFailureSurvivesJournalReloadWithoutParsingCopy() throws {
    var message = ChatMessage(id: "failed-turn", text: "Localized copy", sender: .ai, journalStatus: .failed)
    message.failureCode = .authentication
    let write = message.journalWrite(origin: "main_chat", status: .failed)
    var row = write.dictionary
    row["turnId"] = message.id
    let turn = try XCTUnwrap(KernelJournalTurn(dictionary: row))
    let reloaded = turn.chatMessage()
    XCTAssertEqual(reloaded.failureCode, .authentication)
    XCTAssertEqual(ChatTurnFailurePresentation.of(reloaded), .sessionExpired)
  }

  func testThirdPartyAndByok401DoNotRefreshOmiSession() {
    for (code, provider) in [
      (AgentRuntimeFailureCode.authentication, "anthropic"), (.providerSetupNeeded, "omi"), (.unknown, "anthropic"),
    ] {
      let error = BridgeError.agentRuntimeFailure(
        AgentRuntimeFailure(
          code: "provider_auth_required", failureCode: code,
          userMessage: "HTTP 401 status code (no body)", technicalMessage: "401 invalid_token", provider: provider))
      XCTAssertFalse(error.isSessionAuthenticationFailure)
      XCTAssertNil(ChatErrorState.from(error))
    }
  }
}
