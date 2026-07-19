import XCTest

@testable import Omi_Computer

/// Regression coverage for `AppDetailSheet.primaryAppAction`. The detail-sheet
/// primary button previously derived its label and its action independently: an
/// enabled non-external app showed an "Open" label whose action fell through to a
/// destructive `toggleApp` (disable), silently uninstalling the app on tap. The
/// action is now derived once from (isEnabled, worksExternally) so label and
/// behavior cannot diverge.
final class AppsPagePrimaryActionTests: XCTestCase {

  func testNotEnabledInstalls() {
    XCTAssertEqual(
      AppDetailSheet.primaryAppAction(isEnabled: false, worksExternally: false), .install)
    XCTAssertEqual(
      AppDetailSheet.primaryAppAction(isEnabled: false, worksExternally: true), .install)
  }

  func testEnabledExternalOpens() {
    XCTAssertEqual(
      AppDetailSheet.primaryAppAction(isEnabled: true, worksExternally: true), .open)
  }

  func testEnabledNonExternalHasNoPrimaryAction() {
    // The regression case: previously "Open" → destructive disable. There is
    // no open target for an enabled non-external app, so no primary button.
    XCTAssertEqual(
      AppDetailSheet.primaryAppAction(isEnabled: true, worksExternally: false), .hidden)
  }
}
