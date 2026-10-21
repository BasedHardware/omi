import XCTest

@testable import Omi_Computer

/// Regression coverage for `AppSetupURL.withUID(_:uid:)`.
///
/// `authSteps[].url`/`setupCompletedUrl` come from third-party app manifests.
/// The previous `"\(url)?uid=\(uid)"` concatenation produced
/// `https://x/setup?a=b?uid=u` for a query-bearing base — `uid` landed inside
/// another parameter's value, so the setup page opened unattributed and the
/// completion poll could never report `is_setup_completed`.
final class AppSetupURLTests: XCTestCase {

  private func uidValue(in url: URL?) -> String? {
    url.flatMap { URLComponents(url: $0, resolvingAgainstBaseURL: false) }?
      .queryItems?
      .first(where: { $0.name == "uid" })?
      .value
  }

  func testPlainURLGetsQuestionMarkSeparator() throws {
    let url = try XCTUnwrap(AppSetupURL.withUID("https://example.com/setup", uid: "u1"))
    XCTAssertEqual(url.absoluteString, "https://example.com/setup?uid=u1")
  }

  /// The shipped bug: a base that already carries a query must get `&uid=`,
  /// not a second `?` that swallows the parameter.
  func testQueryBearingURLKeepsUIDAsItsOwnParameter() throws {
    let url = try XCTUnwrap(
      AppSetupURL.withUID("https://example.com/setup?source=omi", uid: "u1"))
    XCTAssertEqual(uidValue(in: url), "u1")
    XCTAssertEqual(
      URLComponents(url: url, resolvingAgainstBaseURL: false)?
        .queryItems?
        .first(where: { $0.name == "source" })?
        .value,
      "omi")
  }

  func testFragmentStaysAfterTheQuery() throws {
    let url = try XCTUnwrap(
      AppSetupURL.withUID("https://example.com/setup#step2", uid: "u1"))
    XCTAssertEqual(url.absoluteString, "https://example.com/setup?uid=u1#step2")
  }

  /// A uid containing query metacharacters must survive the round trip.
  func testSpecialCharacterUIDRoundTrips() throws {
    let url = try XCTUnwrap(
      AppSetupURL.withUID("https://example.com/setup?a=b", uid: "u&x=1#f"))
    XCTAssertEqual(uidValue(in: url), "u&x=1#f")
  }

  /// A provider URL can carry an already-encoded query (signed state, etc.).
  /// Appending uid must not decode/re-encode those bytes.
  func testExistingPercentEncodedQueryIsPreservedVerbatim() throws {
    let url = try XCTUnwrap(
      AppSetupURL.withUID("https://example.com/setup?state=a%2Fb%2Bc", uid: "u1"))
    XCTAssertEqual(url.absoluteString, "https://example.com/setup?state=a%2Fb%2Bc&uid=u1")
  }

  /// A base that already carries `uid` must hand off exactly one — ours.
  func testExistingUIDParameterIsReplacedNotDuplicated() throws {
    let url = try XCTUnwrap(
      AppSetupURL.withUID("https://example.com/setup?uid=stale&x=1", uid: "u1"))
    XCTAssertEqual(
      URLComponents(url: url, resolvingAgainstBaseURL: false)?
        .queryItems?
        .filter { $0.name == "uid" }
        .map(\.value),
      ["u1"])
  }

  func testInvalidBaseResolvesNil() {
    XCTAssertNil(AppSetupURL.withUID("", uid: "u1"))
  }
}
