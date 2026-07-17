import XCTest

@testable import Omi_Computer

final class ChatFirstDeferralOutboxDriverTests: XCTestCase {
  func testDeferredOptionRetainsItsWireKey() throws {
    let request = try XCTUnwrap(
      ChatFirstDeferralDeliveryRequest(payload: [
        "ownerId": "owner-1",
        "continuityKey": "continuity-1",
        "controlGeneration": 1,
        "subject": ["kind": "goal", "id": "goal-1"],
        "question": [
          "questionId": "question-1",
          "text": "What should happen next?",
          "subject": ["kind": "goal", "id": "goal-1"],
          "options": [
            [
              "optionId": "later",
              "label": "Ask tomorrow",
              "preparedAnswer": "Ask me again tomorrow.",
              "defer": true,
            ]
          ],
        ],
        "attemptCount": 1,
        "deliveryGeneration": 1,
        "payloadHash": "hash-1",
      ]))

    XCTAssertTrue(request.question.options[0].isDeferred)
    let data = try JSONEncoder().encode(request.question)
    let wire = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let option = try XCTUnwrap((wire["options"] as? [[String: Any]])?.first)
    XCTAssertEqual(option["defer"] as? Bool, true)
    XCTAssertNil(option["isDeferred"])
  }

  func testDeferralDeliveryRetriesTransientAndServerFailuresOnly() {
    for status in [408, 425, 429, 500, 503] {
      XCTAssertEqual(
        AgentRuntimeProcess.boundedChatFirstDeferralErrorCode(
          for: APIError.httpError(statusCode: status)
        ),
        "chat_first_deferral_retryable"
      )
    }
    for status in [400, 401, 403, 422] {
      XCTAssertEqual(
        AgentRuntimeProcess.boundedChatFirstDeferralErrorCode(
          for: APIError.httpError(statusCode: status)
        ),
        "chat_first_deferral_4xx"
      )
    }
  }

  func testRestartCandidateRequiresTheExactTailUserAndHiddenAssistantPair() {
    let key = "qri_test"
    let candidate = ChatQuestionCardContinuation.tailResumeCandidate(from: [
      ChatMessage(id: "parent", text: "Which goal?", sender: .ai),
      ChatMessage(id: "user", clientTurnId: key, text: "Keep it", sender: .user),
      ChatMessage(
        id: "assistant",
        clientTurnId: key,
        text: "",
        sender: .ai,
        isStreaming: true,
        hidesEmptyStreamingPlaceholder: true
      ),
    ])
    XCTAssertEqual(candidate?.continuityKey, key)
    XCTAssertEqual(candidate?.preparedAnswer, "Keep it")
    XCTAssertEqual(candidate?.assistantTurnID, "assistant")

    XCTAssertNil(
      ChatQuestionCardContinuation.tailResumeCandidate(from: [
        ChatMessage(id: "user", clientTurnId: key, text: "Keep it", sender: .user),
        ChatMessage(
          id: "assistant",
          clientTurnId: key,
          text: "",
          sender: .ai,
          isStreaming: true,
          hidesEmptyStreamingPlaceholder: true
        ),
        ChatMessage(id: "later", text: "A later Omi bubble", sender: .ai),
      ]))
  }
}
