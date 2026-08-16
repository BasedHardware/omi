import XCTest

@testable import Omi_Computer

final class AgentRuntimeFailureTests: XCTestCase {
  func testDetailedAdapterFailureRetainsClosedWireTaxonomy() {
    let failure = AgentRuntimeFailure.parse(from: [
      "code": "adapter_process_exited",
      "failureCode": "transport_interruption",
      "userMessage": "The local agent connection ended.",
      "technicalMessage": "process exited with code 7",
    ])

    XCTAssertEqual(failure?.code, "adapter_process_exited")
    XCTAssertEqual(failure?.failureCode, .transportInterruption)
  }

  func testUnknownWireTaxonomyFailsClosed() {
    let failure = AgentRuntimeFailure.parse(from: [
      "code": "future_adapter_error",
      "failureCode": "unrecognized_future_value",
      "userMessage": "Agent run failed",
    ])

    XCTAssertEqual(failure?.failureCode, .unknown)
  }
}
