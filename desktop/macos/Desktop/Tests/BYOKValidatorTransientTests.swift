import XCTest

@testable import Omi_Computer

/// A provider-validation outcome that says nothing about the key (transport
/// failure, timeout, provider 5xx/429, offline) must never tear down a BYOK
/// enrollment. The reconciler used to treat every non-ok result as a
/// rejection: one offline launch deactivated the server-side free-plan flag
/// while the key text stayed in Settings, and every later chat silently rode
/// the managed lane into billing 402s. These pin the classification boundary
/// and the decision rule both reconciliation paths share.
final class BYOKValidatorTransientTests: XCTestCase {
  func testTransportAndServerFailuresAreTransientNotRejections() {
    XCTAssertTrue(BYOKValidator.isTransient(.transient("The Internet connection appears to be offline.")))
    XCTAssertTrue(BYOKValidator.isTransient(.transient("HTTP 502")))
    XCTAssertTrue(BYOKValidator.isTransient(.transient("HTTP 503")))
    XCTAssertTrue(BYOKValidator.isTransient(.transient("HTTP 429")))
    XCTAssertTrue(BYOKValidator.isTransient(.transient("No HTTP response")))
  }

  func testProviderVerdictsAreNotTransient() {
    XCTAssertFalse(BYOKValidator.isTransient(.ok))
    XCTAssertFalse(BYOKValidator.isTransient(.failed("Rejected (HTTP 401)")))
    XCTAssertFalse(BYOKValidator.isTransient(.failed("Rejected (HTTP 403)")))
    XCTAssertFalse(BYOKValidator.isTransient(.failed("HTTP 400")))
    XCTAssertFalse(BYOKValidator.isTransient(.failed("Empty")))
  }

  func testNotCheckedAndCheckingCarryNoVerdict() {
    XCTAssertFalse(BYOKValidator.isTransient(.notChecked))
    XCTAssertFalse(BYOKValidator.isTransient(.checking))
  }
}
