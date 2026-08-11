import Foundation

/// Where the app sends someone who needs help from a person.
///
/// There used to be a second answer to that — a Crisp thread mounted in Settings, which was
/// asynchronous by construction: you wrote into it and waited for a founder to reply. Discord is
/// the whole answer now, so this is the one link that has to stay correct.
enum SupportLinks {
  /// The invite is spelled out rather than routed through `discord.omi.me`, which the mobile app
  /// uses: that host answers on plain HTTP only — its TLS port does not respond at all — so reusing
  /// it would hand the browser a cleartext hop to be redirected on. This code resolves to the Omi
  /// guild (`1192313062041067520`), which is the same server that redirect lands on.
  static let discord: URL = {
    guard let url = URL(string: "https://discord.gg/TdRNp5U7cy") else {
      preconditionFailure("SupportLinks.discord is not a parseable URL")
    }
    return url
  }()
}
