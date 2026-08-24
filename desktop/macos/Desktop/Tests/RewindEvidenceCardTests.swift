import XCTest

@testable import Omi_Computer

final class RewindEvidenceCardTests: XCTestCase {
  private let deviceID = "macos_test-device"

  func testProducerMarksAnActualScreenshotAsAnExactRewindFrame() throws {
    XCTAssertEqual(
      ScreenCandidateAdapter.evidenceVersion(for: 42),
      RewindEvidenceCardPolicy.supportedVersion
    )
    let decision = ScreenCandidateAdapter.adapt(
      task: makeExtractedTask(),
      dueAt: nil,
      localEvidenceID: "screen-42",
      deviceID: deviceID,
      evidenceVersion: ScreenCandidateAdapter.evidenceVersion(for: 42)
    )
    let evidence = try XCTUnwrap(decision.candidateEvidenceRefs.first)

    XCTAssertEqual(evidence.id, "screen-42")
    XCTAssertEqual(evidence.version, "rewind_frame.v1")
    XCTAssertEqual(
      RewindEvidenceCardPolicy.card(for: evidence, currentDeviceID: deviceID)?.screenshotID,
      42
    )
  }

  func testNilScreenshotFallbackCannotCollideIntoARewindFrame() throws {
    XCTAssertEqual(
      ScreenCandidateAdapter.evidenceVersion(for: nil),
      ScreenCandidateAdapter.captureEvidenceVersion
    )
    let fallbackDecision = ScreenCandidateAdapter.adapt(
      task: makeExtractedTask(),
      dueAt: nil,
      localEvidenceID: "screen-42",
      deviceID: deviceID
    )
    let fallback = try XCTUnwrap(fallbackDecision.candidateEvidenceRefs.first)
    let actual = makeEvidence(
      deviceID: deviceID,
      id: fallback.id,
      version: RewindEvidenceCardPolicy.supportedVersion
    )

    XCTAssertEqual(fallback.version, ScreenCandidateAdapter.captureEvidenceVersion)
    XCTAssertEqual(fallback.id, actual.id)
    XCTAssertNil(RewindEvidenceCardPolicy.card(for: fallback, currentDeviceID: deviceID))
    XCTAssertEqual(RewindEvidenceCardPolicy.card(for: actual, currentDeviceID: deviceID)?.screenshotID, 42)
  }

  func testOldCaptureVersionAndLegacyNilVersionRemainTextOnly() {
    let oldCapture = makeEvidence(deviceID: deviceID, id: "screen-7", version: "capture.v2")
    let legacy = makeEvidence(deviceID: deviceID, id: "screen-8", version: nil)

    XCTAssertNil(RewindEvidenceCardPolicy.card(for: oldCapture, currentDeviceID: deviceID))
    XCTAssertNil(RewindEvidenceCardPolicy.card(for: legacy, currentDeviceID: deviceID))
  }

  func testMalformedForeignAndFutureEvidenceRemainTextOnly() {
    let cases = [
      makeEvidence(deviceID: deviceID, id: "42", version: "capture.v2"),
      makeEvidence(deviceID: deviceID, id: "screen-0", version: "capture.v2"),
      makeEvidence(deviceID: deviceID, id: "screen-01", version: "capture.v2"),
      makeEvidence(
        deviceID: "macos_other-device",
        id: "screen-42",
        version: RewindEvidenceCardPolicy.supportedVersion
      ),
      makeEvidence(deviceID: deviceID, id: "screen-42", version: "rewind_frame.v2"),
      OmiAPI.EvidenceRef(id: "screen-42", kind: .conversation, scope: .canonical, version: "capture.v2"),
      OmiAPI.EvidenceRef(id: "screen-42", kind: .local_screen, scope: .canonical, version: "capture.v2"),
    ]

    for evidence in cases {
      XCTAssertNil(
        RewindEvidenceCardPolicy.card(for: evidence, currentDeviceID: deviceID),
        "unexpected card for \(evidence.kind.rawValue):\(evidence.id)"
      )
    }
  }

  func testTaskDetailLocalEvidenceKeepsAnInertRouteWhenItCannotBeValidated() {
    let task = TaskActionItem(
      id: "task-1",
      description: "Review context",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 1),
      source: "screenshot",
      provenance: [
        OmiAPI.EvidenceRef(
          id: "screen-42",
          kind: .local_screen,
          scope: .device_local,
          version: "capture.v3"
        )
      ]
    )

    let links = TaskDetailSourceLinkPolicy.links(for: task)

    XCTAssertEqual(links.first?.route, .rewind)
  }

  func testTaskDetailCurrentDeviceEvidenceCarriesTheExactFrameIntoRewind() throws {
    let task = TaskActionItem(
      id: "task-2",
      description: "Review the captured screen",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 1),
      source: "screenshot",
      provenance: [
        makeEvidence(
          deviceID: ClientDeviceService.shared.clientDeviceId,
          id: "screen-42",
          version: RewindEvidenceCardPolicy.supportedVersion
        )
      ]
    )

    let link = try XCTUnwrap(TaskDetailSourceLinkPolicy.links(for: task).first)

    XCTAssertEqual(link.route, .rewindFrame(id: 42))
    XCTAssertEqual(link.title, "Screen evidence")
  }

  private func makeEvidence(deviceID: String?, id: String, version: String?) -> OmiAPI.EvidenceRef {
    OmiAPI.EvidenceRef(
      deviceId: deviceID,
      id: id,
      kind: .local_screen,
      scope: .device_local,
      version: version
    )
  }

  private func makeExtractedTask() -> ExtractedTask {
    ExtractedTask(
      title: "Review the captured screen",
      description: nil,
      priority: .medium,
      sourceApp: "Messages",
      inferredDeadline: nil,
      confidence: 0.95,
      tags: [],
      sourceCategory: "direct_request",
      sourceSubcategory: "message",
      captureKind: "direct_request",
      owner: "user",
      concreteDeliverable: true,
      publicBroadcast: false,
      directMention: true,
      alreadyDone: false,
      duplicateOf: nil,
      refinesTask: nil,
      ownershipConfidence: 0.95
    )
  }
}

extension ScreenCandidateDecision {
  fileprivate var candidateEvidenceRefs: [OmiAPI.EvidenceRef] {
    guard let candidate else { return [] }
    switch candidate {
    case .taskCreate(let candidate): return candidate.evidenceRefs
    case .taskUpdate(let candidate): return candidate.evidenceRefs
    case .taskComplete(let candidate): return candidate.evidenceRefs
    case .taskCancel(let candidate): return candidate.evidenceRefs
    case .taskSupersede(let candidate): return candidate.evidenceRefs
    case .workstreamCreate(let candidate): return candidate.evidenceRefs
    }
  }
}
