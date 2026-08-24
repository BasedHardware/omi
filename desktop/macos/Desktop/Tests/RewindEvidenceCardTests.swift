import XCTest

@testable import Omi_Computer

final class RewindEvidenceCardTests: XCTestCase {
  private let deviceID = "macos_test-device"

  func testCurrentDeviceLocalCaptureV2EvidenceBecomesARewindCard() {
    let evidence = makeEvidence(deviceID: deviceID, id: "screen-42", version: "capture.v2")

    let card = RewindEvidenceCardPolicy.card(for: evidence, currentDeviceID: deviceID)

    XCTAssertEqual(card?.screenshotID, 42)
    XCTAssertEqual(card?.subtitle, "Open Rewind · frame 42")
  }

  func testLegacyVersionWithoutVersionStillNeedsTheLocalIdentityFence() {
    let evidence = makeEvidence(deviceID: deviceID, id: "screen-7", version: nil)

    XCTAssertEqual(
      RewindEvidenceCardPolicy.card(for: evidence, currentDeviceID: deviceID)?.screenshotID,
      7
    )
    XCTAssertNil(RewindEvidenceCardPolicy.card(for: evidence, currentDeviceID: "macos_other-device"))
  }

  func testMalformedForeignAndFutureEvidenceRemainTextOnly() {
    let cases = [
      makeEvidence(deviceID: deviceID, id: "42", version: "capture.v2"),
      makeEvidence(deviceID: deviceID, id: "screen-0", version: "capture.v2"),
      makeEvidence(deviceID: deviceID, id: "screen-01", version: "capture.v2"),
      makeEvidence(deviceID: "macos_other-device", id: "screen-42", version: "capture.v2"),
      makeEvidence(deviceID: deviceID, id: "screen-42", version: "capture.v3"),
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
          version: "capture.v2"
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
}
