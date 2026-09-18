import Foundation
import Security

/// Whether *this* running bundle is allowed to replace itself with one it downloaded.
///
/// The question is not rhetorical, and the reason it has its own type is that four builds of this app
/// exist on a developer's Mac at once — the one in `/Applications`, the one still in `build/`,
/// whatever `swift run` produced, and the XCTest runner — and exactly one of them may ever take an
/// update. Omi solves the same problem with `AppBuild.allowsSparkleUpdates`; this is the same idea
/// narrowed to what this package can actually check about itself.
///
/// **Every refusal below is a refusal to *start* Sparkle, not a refusal to check.** That distinction
/// is why the decision is made here, before `SPUStandardUpdaterController` is constructed: Sparkle's
/// controller calls `abort()` — a hard process kill, not a thrown error — when `startUpdater` fails,
/// and starting it with the placeholder `SUPublicEDKey` this repository ships *is* such a failure. A
/// policy consulted after construction would be a policy consulted after the crash.
///
/// The interesting condition is ``Refusal/signedWithoutATeam``, and it is here because of a real
/// failure rather than a hypothetical one. This app's whole value rests on three TCC grants — Screen
/// Recording, Microphone, System Audio — and macOS attaches those grants to a code-signing identity,
/// not to a path or a bundle id. Re-signing the installed bundle with a different identity silently
/// revoked its Screen Recording grant on this very machine: audio kept flowing, screen capture went
/// to zero frames, and the app said nothing for a day. An update *is* a re-sign of the installed
/// bundle. So a build signed with a self-signed local certificate — the `Omi Local Dev Signing`
/// identity has no Team ID — must never pull down a Developer-ID-signed release and install it over
/// itself, because doing so is exactly that failure, delivered automatically. Shipping releases are
/// Developer-ID signed and therefore always carry a Team ID; a locally built bundle never does. That
/// single bit is the line, and it needs no build-time configuration to draw.
enum UpdatePolicy {

  /// The one bundle identifier that ships. Named test bundles, dev variants and any future
  /// side-by-side build get a different identifier and are refused by that alone.
  static let shippingBundleIdentifier = "com.omi.context-for-claude"

  /// The one appcast this app reads: the `appcast.xml` asset on this app's own fixed
  /// `context-for-claude-appcast` GitHub release tag. No backend is involved in updates at all —
  /// the enclosures inside that feed are this app's own `context-for-claude-v*` release assets.
  ///
  /// A *mutable tag with a replaced asset* rather than a file committed next to this source, because
  /// an appcast can only be written after the archive it signs exists: its `edSignature` is of the
  /// packaged ZIP. Committing one would therefore mean a push to `main` on every release, which this
  /// repository forbids. Replacing an asset on a fixed tag needs no git write.
  static let releaseFeedURL =
    "https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml"

  /// Background downloading is safe once Sparkle has verified the feed and archive. Replacing the
  /// running bundle is not: it must remain behind an explicit user approval and relaunch.
  static let automaticallyDownloadsUpdates = true
  static let requiresRelaunchConfirmation = true

  enum RelaunchState: Equatable, Sendable {
    case idle
    case required(version: String)

    var message: String? {
      switch self {
      case .idle:
        return nil
      case .required(let version):
        return "Context for Claude update \(version) is downloaded and verified. "
          + "Choose Install and Relaunch to apply it."
      }
    }
  }

  static let relaunchPromptTitle = "Context for Claude update ready"

  static func relaunchPromptMessage(for version: String) -> String {
    "Version \(version) has been downloaded and verified. Installing it will briefly stop "
      + "capture while Context for Claude relaunches. Install and relaunch now?"
  }

  /// What `Resources/Info.plist` carries until a maintainer runs `generate_keys`. Compared exactly:
  /// the value is not a key, is not decodable as one, and must never be treated as configuration.
  static let publicKeyPlaceholder = "REPLACE_WITH_SUPublicEDKey_FROM_generate_keys"

  /// The environment variable that turns the updater off for a run. Off only — there is no
  /// corresponding variable that turns it *on*, because every refusal below exists to stop an
  /// unsafe install and an override would be a way to ask for one.
  static let disableEnvironmentVariable = "CONTEXT_DISABLE_UPDATES"

  /// Why the updater is not running. Raw values are the slugs that reach `record_fallback`, so they
  /// are fixed, lowercase and carry no user text.
  enum Refusal: String, Equatable, Sendable {
    /// A dev build, a named test bundle, a `swift run` process, or the XCTest runner — anything
    /// whose identifier is not the shipping one, including the `nil` an unbundled process has.
    case notTheShippingBundle = "not-the-shipping-bundle"
    /// `SUPublicEDKey` is missing, still the placeholder, or not a 32-byte base64 key. Sparkle
    /// cannot verify a signature without it, and an updater that cannot verify a signature is a
    /// remote code execution channel with a progress bar.
    case updateKeyNotConfigured = "update-key-not-configured"
    /// `SUFeedURL` is missing, is not `https`, or is not this app's own product-scoped release
    /// asset. Plain `http`, another product's tag, and the repository-wide `releases/latest` feed
    /// are refused outright rather than warned about: the EdDSA signature authenticates an artifact,
    /// not the product identity it replaces.
    case feedNotConfigured = "feed-not-configured"
    /// Signed by a certificate with no Team ID — a self-signed local identity. See the type's
    /// documentation; this is the TCC-preservation rule, expressed as code.
    case signedWithoutATeam = "signed-without-a-team"
    /// `CONTEXT_DISABLE_UPDATES` is set in this process's environment.
    case disabledByEnvironment = "disabled-by-environment"
  }

  enum Decision: Equatable, Sendable {
    case allowed
    case refused(Refusal)

    var isAllowed: Bool {
      if case .allowed = self { return true }
      return false
    }

    var refusal: Refusal? {
      if case .refused(let reason) = self { return reason }
      return nil
    }
  }

  /// The decision as a pure function of what the bundle says about itself, so every branch is
  /// drivable in a test without a signed app, a keychain, or a network.
  ///
  /// Order matters only in what a person is shown: the checks are listed cheapest-and-most-decisive
  /// first, so a developer running from `build/` is told "this is not the shipping bundle" rather
  /// than being sent to look for a key they never had.
  static func decide(
    bundleIdentifier: String?,
    feedURL: String?,
    publicEDKey: String?,
    teamIdentifier: String?,
    isDisabledByEnvironment: Bool
  ) -> Decision {
    if isDisabledByEnvironment { return .refused(.disabledByEnvironment) }
    guard bundleIdentifier == shippingBundleIdentifier else {
      return .refused(.notTheShippingBundle)
    }
    guard isUsableFeedURL(feedURL) else { return .refused(.feedNotConfigured) }
    guard isConfiguredPublicKey(publicEDKey) else { return .refused(.updateKeyNotConfigured) }
    guard let teamIdentifier, !teamIdentifier.isEmpty else {
      return .refused(.signedWithoutATeam)
    }
    return .allowed
  }

  /// The only feed this app may fetch: its own release asset, at its exact URL.
  ///
  /// Sparkle does not know that Omi Desktop and Context for Claude are different products, and both
  /// publish releases out of this one repository. A feed that is not this app's could therefore
  /// deliver a validly signed Omi Computer bundle and replace this app under Context for Claude's
  /// name and icon — so `github.com` as a host is worth nothing on its own here. The
  /// `context-for-claude-appcast` tag in the path is the product identity, and pinning the *whole*
  /// path is what refuses `releases/latest/download/appcast.xml`: `latest` is the newest release of
  /// the entire monorepo, which publishes Omi Desktop tags several times a day, and it currently
  /// resolves to one. `desktop/windows/docs/release-pipeline.md` rejects that same endpoint for the
  /// same reason.
  ///
  /// **Defense in depth, not the only defense.** The real backstop against a wrong-product install
  /// is key separation: this app ships its own `SUPublicEDKey`, Omi Desktop uses a different pair,
  /// so an Omi enclosure would fail EdDSA verification here whichever feed named it. What this guard
  /// buys is that a mistargeted feed fails closed and *legibly* — a named refusal in Settings rather
  /// than a signature error — which is also why the residual risk of getting this wrong is "updates
  /// silently stop happening", and why the tests over this function are the ones that matter.
  ///
  /// Pinning binds the configured URL, not the bytes' origin: the release-download path answers 302
  /// to `objects.githubusercontent.com`, and Sparkle follows that redirect.
  static func isUsableFeedURL(_ feedURL: String?) -> Bool {
    guard let feedURL, !feedURL.isEmpty, let components = URLComponents(string: feedURL),
      components.scheme?.lowercased() == "https",
      components.host?.lowercased() == "github.com",
      components.port == nil,
      components.user == nil,
      components.password == nil,
      components.path == "/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml",
      components.query == nil,
      components.fragment == nil
    else { return false }

    return true
  }

  /// A configured Sparkle EdDSA public key: base64 for exactly 32 bytes, and not the placeholder.
  ///
  /// The length check is what makes this more than a placeholder comparison. `generate_keys` emits
  /// a 44-character base64 string for a 32-byte Ed25519 public key; anything else — a truncated
  /// paste, a private key copied by mistake, a comment line carried along with the value — is a
  /// build that would abort at launch. Catching it here turns a crash into a disabled updater.
  static func isConfiguredPublicKey(_ publicEDKey: String?) -> Bool {
    guard let publicEDKey else { return false }
    let trimmed = publicEDKey.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty, trimmed != publicKeyPlaceholder else { return false }
    guard let decoded = Data(base64Encoded: trimmed) else { return false }
    return decoded.count == 32
  }

  /// The sentence the Settings row shows when the updater is not running.
  ///
  /// Every one of these is read by somebody who just clicked a button and saw nothing happen, so
  /// each says what this build *is* rather than what it lacks. "Updates are disabled" is the
  /// sentence that sends a developer looking for a bug.
  static func explanation(_ refusal: Refusal) -> String {
    switch refusal {
    case .notTheShippingBundle:
      return "This is a locally built copy, so it doesn't update itself. "
        + "Rebuild from source to move to a newer version."
    case .updateKeyNotConfigured:
      return "This build has no update-signing key, so it can't verify a download. "
        + "It won't update itself."
    case .feedNotConfigured:
      return "This build has no update feed configured, so it won't update itself."
    case .signedWithoutATeam:
      return "This copy is signed with a local development certificate. "
        + "Updating it would reset its Screen Recording and microphone permissions, "
        + "so it doesn't update itself — rebuild from source instead."
    case .disabledByEnvironment:
      return "Updates are turned off for this run by \(disableEnvironmentVariable)."
    }
  }

  // MARK: - What the running process actually is

  /// The live decision for this process.
  static func current(
    bundle: Bundle = .main,
    environment: [String: String] = ProcessInfo.processInfo.environment
  ) -> Decision {
    decide(
      bundleIdentifier: bundle.bundleIdentifier,
      feedURL: bundle.object(forInfoDictionaryKey: "SUFeedURL") as? String,
      publicEDKey: bundle.object(forInfoDictionaryKey: "SUPublicEDKey") as? String,
      teamIdentifier: currentTeamIdentifier(),
      isDisabledByEnvironment: environment[disableEnvironmentVariable] != nil)
  }

  /// The Team ID of the certificate this process is signed with, or `nil` when there is none.
  ///
  /// `nil` covers three cases that all mean the same thing here: unsigned, ad-hoc signed, and
  /// signed with a self-signed certificate that has no Apple team behind it. A Developer ID or
  /// Apple Development certificate always carries one, so a non-nil answer is the only evidence
  /// available at runtime that this bundle came off a real signing identity.
  ///
  /// Asked of the *running code* rather than of the bundle on disk, because those can differ: a
  /// build that replaced `/Applications/Context for Claude.app` while an older copy is still
  /// running would otherwise have the old process reporting the new bundle's identity.
  static func currentTeamIdentifier() -> String? {
    var code: SecCode?
    guard SecCodeCopySelf(SecCSFlags(rawValue: 0), &code) == errSecSuccess, let code else {
      return nil
    }
    var staticCode: SecStaticCode?
    guard SecCodeCopyStaticCode(code, SecCSFlags(rawValue: 0), &staticCode) == errSecSuccess,
      let staticCode
    else { return nil }
    var information: CFDictionary?
    guard
      SecCodeCopySigningInformation(
        staticCode, SecCSFlags(rawValue: kSecCSSigningInformation), &information)
        == errSecSuccess,
      let dictionary = information as? [String: Any]
    else { return nil }
    let team = dictionary[kSecCodeInfoTeamIdentifier as String] as? String
    return (team?.isEmpty ?? true) ? nil : team
  }
}
