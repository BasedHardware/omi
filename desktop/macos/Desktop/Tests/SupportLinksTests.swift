import XCTest

@testable import Omi_Computer

/// The app's one remaining outbound support link.
///
/// `SupportLinks.discord` traps rather than degrading if its string stops parsing, and it is
/// evaluated the first time About is drawn rather than at launch — so without this, a typo in it
/// would first be reported by a user whose app died on the Settings page.
final class SupportLinksTests: XCTestCase {
  func testDiscordInviteCarriesAnInviteCode() {
    XCTAssertEqual(SupportLinks.discord.host, "discord.gg")
    XCTAssertFalse(
      SupportLinks.discord.lastPathComponent.isEmpty,
      "the invite lost its code, so the button now opens Discord's marketing page")
  }

  /// It must not regress to the `discord.omi.me` redirector the mobile app uses: that host serves
  /// plain HTTP only — its TLS port does not answer — so pointing here at it would hand the browser
  /// a cleartext hop for someone on the path to answer instead of Discord.
  func testDiscordInviteIsHTTPS() {
    XCTAssertEqual(SupportLinks.discord.scheme, "https")
  }
}
