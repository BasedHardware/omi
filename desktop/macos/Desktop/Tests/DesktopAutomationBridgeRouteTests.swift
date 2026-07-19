import XCTest

@testable import Omi_Computer

private struct ImmediatePresentationTimeoutWaiter: DesktopAutomationPresentationTimeoutWaiting {
  func waitForTimeout() async {}
}

private struct AutomationCapabilitiesEnvelope: Decodable {
  let ok: Bool
  let result: DesktopAutomationCapabilities?
  let error: String?
}

private struct AutomationErrorEnvelope: Decodable {
  let ok: Bool
  let error: String?
}

@MainActor
private final class StubPresentationCoordinator: DesktopAutomationPresentationCoordinating {
  private(set) var calls: [(target: DesktopAutomationPresentationTarget, gate: DesktopAutomationPresentationGate)] = []
  var failure: DesktopAutomationPresentationFailure?

  func present(
    _ target: DesktopAutomationPresentationTarget,
    gate: DesktopAutomationPresentationGate
  ) async -> DesktopAutomationPresentationResolution {
    calls.append((target, gate))
    if let failure {
      return .failed(failure)
    }
    return .presented(
      DesktopAutomationPresentationCommand(
        generation: UInt64(calls.count),
        target: target
      ))
  }
}

@MainActor
final class DesktopAutomationBridgeRouteTests: XCTestCase {
  func testUnauthenticatedHealthReportsBackendAndRuntimeProtocolIdentity() async throws {
    let response = await DesktopAutomationBridge.shared.response(
      for: DesktopAutomationHTTPRequest(
        method: "GET",
        path: "/health",
        headers: ["host": "127.0.0.1:\(DesktopAutomationLaunchOptions.port)"],
        body: Data()
      )
    )

    XCTAssertEqual(response.statusCode, 200)
    let object = try XCTUnwrap(
      JSONSerialization.jsonObject(with: response.body) as? [String: Any]
    )
    XCTAssertEqual(object["requiresAuth"] as? Bool, true)
    XCTAssertNotNil(object["backendEnvironment"] as? String)
    XCTAssertNotNil(object["pythonBackendURL"] as? String)
    XCTAssertNotNil(object["rustBackendURL"] as? String)
    XCTAssertNotNil(object["processID"] as? Int)
    XCTAssertEqual(object["logFilePath"] as? String, omiLogFilePath())
    XCTAssertEqual(object["logLaunchID"] as? String, omiLogLaunchID())
    XCTAssertNotNil(object["agentRuntimeRunning"] as? Bool)
    XCTAssertEqual(
      object["agentRuntimeExpectedProtocolVersion"] as? Int,
      AgentRuntimeProcess.expectedProtocolVersion
    )
    if object["agentRuntimeRunning"] as? Bool == true {
      XCTAssertNotNil(object["agentRuntimeProtocolVersion"] as? Int)
      XCTAssertNotNil(object["agentRuntimeVersion"] as? String)
    }
  }

  func testPresentationReadinessDefersAndPreservesTheExactActiveCommand() {
    var readiness = DesktopAutomationPresentationReadinessGate()
    let command = DesktopAutomationPresentationCommand(
      generation: 42,
      target: .importConnector("chatgpt")
    )

    XCTAssertNil(readiness.commandForConsumption(command))
    XCTAssertNil(readiness.transition(to: false, activeCommand: command))
    XCTAssertEqual(readiness.transition(to: true, activeCommand: command), command)
    XCTAssertEqual(readiness.commandForConsumption(command), command)

    let nextCommand = DesktopAutomationPresentationCommand(
      generation: 43,
      target: .exportDestination("notion")
    )
    XCTAssertEqual(readiness.commandForConsumption(nextCommand), nextCommand)
    XCTAssertNil(readiness.transition(to: false, activeCommand: nextCommand))
    XCTAssertNil(readiness.commandForConsumption(nextCommand))
  }

  func testPresentationRoutesAdvertiseImportAndExportCapabilities() {
    XCTAssertEqual(
      Set(DesktopAutomationPresentationRoute.allCases.map(\.capability)),
      ["POST /open-export", "POST /open-import"]
    )
  }

  func testProductionRouteEncodesPresentationCapabilitiesAsJSON() async throws {
    let response = await DesktopAutomationBridge.shared.response(
      for: authorizedRequest(method: "GET", path: "/capabilities")
    )

    XCTAssertEqual(response.statusCode, 200)
    XCTAssertEqual(response.headers["Content-Type"], "application/json")
    let envelope = try JSONDecoder().decode(
      AutomationCapabilitiesEnvelope.self, from: response.body)
    XCTAssertTrue(envelope.ok)
    XCTAssertNil(envelope.error)
    let capabilities = try XCTUnwrap(envelope.result)
    XCTAssertEqual(capabilities.schemaVersion, 2)
    XCTAssertTrue(capabilities.routes.contains("GET /capabilities"))
    XCTAssertTrue(capabilities.routes.contains("POST /open-import"))
    XCTAssertTrue(capabilities.routes.contains("POST /open-export"))
    XCTAssertEqual(
      Set(capabilities.routes).intersection(
        DesktopAutomationPresentationRoute.allCases.map(\.capability)),
      Set(DesktopAutomationPresentationRoute.allCases.map(\.capability))
    )
    XCTAssertTrue(
      String(decoding: response.serializedHTTP1Data(), as: UTF8.self)
        .hasPrefix("HTTP/1.1 200 OK\r\n")
    )
  }

  func testProductionPresentationRouteEncodesInvalidRequestJSON() async throws {
    let response = await DesktopAutomationBridge.shared.response(
      for: authorizedRequest(
        method: "POST",
        path: DesktopAutomationPresentationRoute.openImport.rawValue,
        body: Data("{}".utf8)
      )
    )

    XCTAssertEqual(response.statusCode, 400)
    XCTAssertEqual(response.headers["Content-Type"], "application/json")
    let envelope = try JSONDecoder().decode(AutomationErrorEnvelope.self, from: response.body)
    XCTAssertFalse(envelope.ok)
    XCTAssertEqual(envelope.error, "invalid_request")
    XCTAssertTrue(
      String(decoding: response.serializedHTTP1Data(), as: UTF8.self)
        .hasPrefix("HTTP/1.1 400 Bad Request\r\n")
    )
  }

  func testHTTPSerializerUsesPresentationFailureReasonPhrases() {
    let expectedStatusLines = [
      409: "HTTP/1.1 409 Conflict",
      503: "HTTP/1.1 503 Service Unavailable",
      504: "HTTP/1.1 504 Gateway Timeout",
    ]

    for (statusCode, expectedStatusLine) in expectedStatusLines {
      let response = DesktopAutomationHTTPResponse(
        statusCode: statusCode,
        headers: ["Content-Type": "application/json"],
        body: Data("{\"ok\":false}".utf8)
      )
      let serialized = String(decoding: response.serializedHTTP1Data(), as: UTF8.self)
      XCTAssertEqual(serialized.components(separatedBy: "\r\n").first, expectedStatusLine)
      XCTAssertTrue(serialized.hasSuffix("{\"ok\":false}"))
    }
  }

  func testSignedOutAndOnboardingRequestsFailWithoutPublishingCommands() async {
    let coordinator = DesktopAutomationPresentationCoordinator(
      timeoutWaiter: ImmediatePresentationTimeoutWaiter())

    let signedOut = await coordinator.present(
      .importConnector("chatgpt"),
      gate: .signedOut
    )
    XCTAssertEqual(signedOut, .failed(.signedOut))
    XCTAssertNil(coordinator.activeCommand)

    let onboarding = await coordinator.present(
      .exportDestination("notion"),
      gate: .onboardingIncomplete
    )
    XCTAssertEqual(onboarding, .failed(.onboardingIncomplete))
    XCTAssertNil(coordinator.activeCommand)
  }

  func testMatchingVisibleAcknowledgementCompletesExactCommand() async {
    let coordinator = DesktopAutomationPresentationCoordinator(
      timeoutWaiter: ImmediatePresentationTimeoutWaiter())
    let command = coordinator.beginPresentation(.importConnector("chatgpt"))

    XCTAssertTrue(
      coordinator.acknowledgeVisible(
        generation: command.generation,
        target: .importConnector("chatgpt")
      ))

    let resolution = await coordinator.waitForResolution(of: command)
    XCTAssertEqual(resolution, .presented(command))
    XCTAssertNil(coordinator.activeCommand)
  }

  func testStaleAndWrongAcknowledgementsCannotSatisfyNewerCommand() async {
    let coordinator = DesktopAutomationPresentationCoordinator(
      timeoutWaiter: ImmediatePresentationTimeoutWaiter())
    let first = coordinator.beginPresentation(.importConnector("chatgpt"))
    let second = coordinator.beginPresentation(.exportDestination("notion"))

    XCTAssertFalse(
      coordinator.acknowledgeVisible(
        generation: first.generation,
        target: first.target
      ))
    XCTAssertFalse(
      coordinator.acknowledgeVisible(
        generation: second.generation,
        target: .exportDestination("obsidian")
      ))
    let firstResolution = await coordinator.waitForResolution(of: first)
    XCTAssertEqual(firstResolution, .failed(.superseded))

    XCTAssertTrue(
      coordinator.acknowledgeVisible(
        generation: second.generation,
        target: second.target
      ))
    let secondResolution = await coordinator.waitForResolution(of: second)
    XCTAssertEqual(secondResolution, .presented(second))
  }

  func testInjectedWaiterProducesDeterministicRouteTimeout() async {
    let coordinator = DesktopAutomationPresentationCoordinator(
      timeoutWaiter: ImmediatePresentationTimeoutWaiter())
    let handler = DesktopAutomationPresentationRequestHandler(coordinator: coordinator)

    let result = await handler.openImport(
      identifier: "chatgpt",
      knownIdentifiers: ["chatgpt"],
      gate: .ready
    )

    XCTAssertEqual(result.failure, .routeTimedOut)
    XCTAssertEqual(result.errorCode, "route_timed_out")
    XCTAssertEqual(result.statusCode, 504)
    XCTAssertNil(coordinator.activeCommand)
  }

  func testNewestConcurrentRequestSupersedesPriorRequest() async {
    let coordinator = DesktopAutomationPresentationCoordinator(
      timeoutWaiter: ImmediatePresentationTimeoutWaiter())
    let first = coordinator.beginPresentation(.importConnector("chatgpt"))
    let second = coordinator.beginPresentation(.importConnector("claude"))

    let firstResolution = await coordinator.waitForResolution(of: first)
    XCTAssertEqual(firstResolution, .failed(.superseded))
    XCTAssertEqual(coordinator.activeCommand, second)

    XCTAssertTrue(
      coordinator.rejectUnavailable(
        generation: second.generation,
        target: second.target
      ))
    let secondResolution = await coordinator.waitForResolution(of: second)
    XCTAssertEqual(secondResolution, .failed(.presentationUnavailable))
  }

  func testAlreadyVisibleTargetCanAcknowledgeTheNextGeneration() async {
    let coordinator = DesktopAutomationPresentationCoordinator(
      timeoutWaiter: ImmediatePresentationTimeoutWaiter())
    let first = coordinator.beginPresentation(.importConnector("chatgpt"))

    XCTAssertTrue(
      coordinator.acknowledgeVisible(
        generation: first.generation,
        target: first.target
      ))
    let firstResolution = await coordinator.waitForResolution(of: first)
    XCTAssertEqual(firstResolution, .presented(first))

    let second = coordinator.beginPresentation(.importConnector("chatgpt"))
    XCTAssertTrue(
      coordinator.acknowledgeVisible(
        generation: second.generation,
        target: second.target
      ))
    let secondResolution = await coordinator.waitForResolution(of: second)
    XCTAssertEqual(secondResolution, .presented(second))
  }

  func testHandlerValidatesAndForwardsImportAndExportTargets() async {
    let coordinator = StubPresentationCoordinator()
    let handler = DesktopAutomationPresentationRequestHandler(coordinator: coordinator)

    let importResult = await handler.openImport(
      identifier: "chatgpt",
      knownIdentifiers: ["chatgpt", "claude"],
      gate: .ready
    )
    let exportResult = await handler.openExport(
      identifier: "notion",
      knownIdentifiers: ["notion", "obsidian"],
      gate: .ready
    )

    XCTAssertEqual(importResult.statusCode, 200)
    XCTAssertEqual(importResult.command?.target, .importConnector("chatgpt"))
    XCTAssertEqual(exportResult.statusCode, 200)
    XCTAssertEqual(exportResult.command?.target, .exportDestination("notion"))
    XCTAssertEqual(coordinator.calls.count, 2)
    XCTAssertEqual(coordinator.calls[0].target, .importConnector("chatgpt"))
    XCTAssertEqual(coordinator.calls[1].target, .exportDestination("notion"))
  }

  func testHandlerReturnsStableUnknownAndAppStateFailures() async {
    let coordinator = StubPresentationCoordinator()
    let handler = DesktopAutomationPresentationRequestHandler(coordinator: coordinator)

    let unknownImport = await handler.openImport(
      identifier: "missing",
      knownIdentifiers: ["chatgpt"],
      gate: .ready
    )
    let unknownExport = await handler.openExport(
      identifier: "missing",
      knownIdentifiers: ["notion"],
      gate: .ready
    )

    XCTAssertEqual(unknownImport.failure, .unknownConnector)
    XCTAssertEqual(unknownImport.errorCode, "connector_unknown")
    XCTAssertEqual(unknownImport.statusCode, 400)
    XCTAssertEqual(unknownExport.failure, .unknownDestination)
    XCTAssertEqual(unknownExport.errorCode, "destination_unknown")
    XCTAssertEqual(unknownExport.statusCode, 400)
    XCTAssertTrue(coordinator.calls.isEmpty)

    coordinator.failure = .presentationUnavailable
    let unavailable = await handler.openImport(
      identifier: "chatgpt",
      knownIdentifiers: ["chatgpt"],
      gate: .ready
    )
    XCTAssertEqual(unavailable.errorCode, "sheet_not_visible")
    XCTAssertEqual(unavailable.statusCode, 503)
  }

  private func authorizedRequest(
    method: String,
    path: String,
    body: Data = Data()
  ) -> DesktopAutomationHTTPRequest {
    DesktopAutomationHTTPRequest(
      method: method,
      path: path,
      headers: [
        "host": "127.0.0.1:\(DesktopAutomationLaunchOptions.port)",
        "authorization": "Bearer \(DesktopAutomationLaunchOptions.token)",
      ],
      body: body
    )
  }
}
