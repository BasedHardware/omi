import Foundation
import XCTest

@testable import ContextApp

/// An auto-updater is the only feature in this app that can replace the app.
///
/// Everything here guards the same boundary from a different side: which builds are allowed to do
/// that, which feed they are allowed to do it from, and what the app has to remember afterwards.
/// `UpdatePolicy.decide` is a pure function precisely so these can be written without a signed
/// bundle, a keychain or a network — the alternative is a policy exercised only in production, on
/// the one code path where being wrong costs the user every permission they ever granted.
final class UpdatePolicyTests: XCTestCase {

  /// A well-formed stand-in for what `generate_keys` prints: 32 bytes, base64.
  private static let realShapedKey = Data(repeating: 0x2A, count: 32).base64EncodedString()
  private static let shippingFeed = UpdatePolicy.releaseFeedURL

  private func decide(
    bundleIdentifier: String? = UpdatePolicy.shippingBundleIdentifier,
    feedURL: String? = UpdatePolicyTests.shippingFeed,
    publicEDKey: String? = UpdatePolicyTests.realShapedKey,
    teamIdentifier: String? = "ABCDE12345",
    isDisabledByEnvironment: Bool = false
  ) -> UpdatePolicy.Decision {
    UpdatePolicy.decide(
      bundleIdentifier: bundleIdentifier,
      feedURL: feedURL,
      publicEDKey: publicEDKey,
      teamIdentifier: teamIdentifier,
      isDisabledByEnvironment: isDisabledByEnvironment)
  }

  // MARK: - The shipping build

  /// The control. Without it every refusal below could be produced by a policy that refuses
  /// everything, which would pass this whole file and ship an app that never updates.
  func testAProperlySignedShippingBundleWithARealKeyAndFeedIsAllowed() {
    XCTAssertEqual(decide(), .allowed)
  }

  // MARK: - Local builds must not update themselves

  /// **The regression test for the failure this policy exists to prevent.**
  ///
  /// macOS attaches Screen Recording, Microphone and System Audio consent to a code signature, not
  /// to a path. On the machine this was written on, re-signing the installed bundle revoked its
  /// Screen Recording grant: audio went on recording, screen capture returned zero frames for a
  /// day, and nothing anywhere said so. Installing an update *is* re-signing the installed bundle
  /// with whatever identity built the release. A copy signed with the local `Omi Local Dev Signing`
  /// certificate — which has no Team ID — pulling down a Developer-ID-signed release would
  /// reproduce that failure automatically, on purpose, on a schedule.
  func testALocallySignedCopyWithNoTeamIdentifierRefusesToUpdateItself() {
    XCTAssertEqual(decide(teamIdentifier: nil), .refused(.signedWithoutATeam))
    XCTAssertEqual(decide(teamIdentifier: ""), .refused(.signedWithoutATeam))
  }

  /// And the refusal has to read as a property of the build rather than as a fault, because the
  /// person reading it is a developer wondering whether they broke the updater.
  func testTheLocalBuildRefusalNamesThePermissionsItIsProtecting() {
    let sentence = UpdatePolicy.explanation(.signedWithoutATeam)
    XCTAssertTrue(sentence.contains("Screen Recording"), sentence)
    XCTAssertTrue(sentence.lowercased().contains("rebuild"), sentence)
  }

  /// A named test bundle, a dev variant, or anything else that is not the one identifier that
  /// ships. `nil` is in here on purpose: that is what `Bundle.main.bundleIdentifier` answers under
  /// `swift run` and inside the XCTest runner, so this is also what stops a test process from
  /// starting a real updater.
  func testOnlyTheShippingBundleIdentifierMayUpdate() {
    for identifier in [
      nil, "", "com.omi.context-for-claude.dev", "com.omi.context-for-claude-test",
      "com.omi.computer-macos",
    ] {
      XCTAssertEqual(
        decide(bundleIdentifier: identifier), .refused(.notTheShippingBundle),
        "\(identifier ?? "nil") must not be allowed to update itself")
    }
  }

  func testTheEnvironmentSwitchTurnsTheUpdaterOffAndIsCheckedFirst() {
    XCTAssertEqual(decide(isDisabledByEnvironment: true), .refused(.disabledByEnvironment))
    // Checked ahead of everything else, so a developer who set it is told that is why, rather
    // than being sent to look at a key or a certificate they did not change.
    XCTAssertEqual(
      decide(bundleIdentifier: nil, teamIdentifier: nil, isDisabledByEnvironment: true),
      .refused(.disabledByEnvironment))
  }

  // MARK: - The signing key

  /// The placeholder this repository ships is not a key, and treating it as one is not a cosmetic
  /// mistake: `SPUStandardUpdaterController(startingUpdater: true, …)` calls `abort()` when the
  /// updater cannot start, so a build that got that far with the placeholder in place would crash
  /// on launch rather than quietly skip updating.
  func testThePlaceholderPublicKeyIsNotConfiguration() {
    XCTAssertFalse(UpdatePolicy.isConfiguredPublicKey(UpdatePolicy.publicKeyPlaceholder))
    XCTAssertEqual(
      decide(publicEDKey: UpdatePolicy.publicKeyPlaceholder),
      .refused(.updateKeyNotConfigured))
  }

  /// Anything that is not exactly a 32-byte base64 blob: absent, blank, truncated by a bad paste,
  /// too long because a private key was copied instead, or not base64 at all.
  func testAMalformedPublicKeyIsRefusedRatherThanHandedToSparkle() {
    let malformed: [String?] = [
      nil,
      "",
      "   ",
      "not base64 at all!!",
      Data(repeating: 0x2A, count: 16).base64EncodedString(),
      Data(repeating: 0x2A, count: 64).base64EncodedString(),
    ]
    for key in malformed {
      XCTAssertEqual(
        decide(publicEDKey: key), .refused(.updateKeyNotConfigured),
        "\(key ?? "nil") must not be accepted as an EdDSA public key")
    }
  }

  /// Surrounding whitespace survives a copy out of `generate_keys`' output and must not turn a
  /// valid key into a disabled updater.
  func testAKeyWithSurroundingWhitespaceIsStillAKey() {
    XCTAssertTrue(UpdatePolicy.isConfiguredPublicKey("  \(Self.realShapedKey)\n"))
  }

  // MARK: - The feed

  /// The contract, spelled out as a literal rather than read back off `UpdatePolicy`, so that moving
  /// the constant cannot quietly move the assertion with it.
  ///
  /// Every part of this URL is load-bearing, and none of it is a preference:
  /// - `https` + `github.com` — updates come from GitHub releases and no backend brokers them; the
  ///   route this app used to read (`api.omi.me/v2/micro-apps/…`) has been deleted.
  /// - `context-for-claude-appcast` — a *fixed* tag whose `appcast.xml` asset is replaced on each
  ///   release. Fixed because it must be knowable at build time; an asset rather than a file
  ///   committed beside this source because an appcast signs an archive that does not exist until the
  ///   release is packaged, so committing one would mean pushing to `main` on every release.
  func testTheContextFeedIsThisAppsOwnGitHubReleaseAsset() {
    XCTAssertEqual(
      UpdatePolicy.releaseFeedURL,
      "https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml"
    )
    XCTAssertTrue(UpdatePolicy.isUsableFeedURL(UpdatePolicy.releaseFeedURL))
  }

  /// Plausible-but-wrong feeds, which is the only kind that gets shipped. Each of these is a URL
  /// somebody could reasonably write down, and each points this app at something that is not this
  /// app — so `isUsableFeedURL` pins the whole URL rather than a host or a prefix.
  func testAPlausibleButWrongFeedIsRefused() {
    let wrong = [
      // The backend route this app used to read. It no longer exists, and no feed may return to a
      // backend: updates have no backend involvement at all.
      "https://api.omi.me/v2/micro-apps/context-for-claude/appcast.xml",
      "https://api.omi.me/v2/desktop/appcast.xml",
      // Another product's tag, in this same repository.
      "https://github.com/BasedHardware/omi/releases/download/omi-desktop-appcast/appcast.xml",
      // A committed appcast on `main` — the design this feed deliberately is not.
      "https://raw.githubusercontent.com/BasedHardware/omi/main/desktop/context-for-claude/appcast.xml",
      // Right tag, wrong repository: a fork could otherwise serve this app its updates.
      "https://github.com/someone-else/omi/releases/download/context-for-claude-appcast/appcast.xml",
      // Right shape, no TLS.
      "http://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml",
      // A host that merely starts with the pinned one.
      "https://github.com.example.invalid/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml",
      // Userinfo, port, query and fragment: each is a way to reach somewhere else, or to make one
      // pinned URL serve two answers.
      "https://someone@github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml",
      "https://github.com:8443/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml",
      "https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml?channel=beta",
      "https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml#beta",
    ]
    for feed in wrong {
      XCTAssertFalse(UpdatePolicy.isUsableFeedURL(feed), "\(feed) must not be usable as a feed")
      XCTAssertEqual(
        decide(feedURL: feed), .refused(.feedNotConfigured),
        "\(feed) must not be accepted as an update feed")
    }
  }

  /// **The other catastrophic misconfiguration, and the reason it is refused in code.**
  ///
  /// `releases/latest` is the newest release of the *whole repository*, not of this app, and this
  /// monorepo publishes several releases a day — at the time of writing `latest` resolves to an Omi
  /// Desktop macOS tag. Sparkle has no idea these are two products: pointed there it would fetch
  /// Omi's enclosure, and if the key ever matched it would replace Context for Claude with Omi
  /// Computer, under this app's name and this app's icon, on every machine at once. The Windows
  /// client refuses the same endpoint for the same reason
  /// (`desktop/windows/docs/release-pipeline.md`). It is not a likely typo; it is a typo whose blast
  /// radius makes review the wrong place to catch it.
  func testTheRepositoryWideLatestReleaseFeedIsRefusedAsAFeedForThisApp() {
    let latest = "https://github.com/BasedHardware/omi/releases/latest/download/appcast.xml"
    XCTAssertFalse(UpdatePolicy.isUsableFeedURL(latest))
    XCTAssertEqual(decide(feedURL: latest), .refused(.feedNotConfigured))
  }

  func testTheFeedMustBePresentAndHTTPS() {
    for feed in [
      nil, "", "not a url at all", "http://example.com/appcast.xml",
      "http://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml",
    ] {
      XCTAssertEqual(
        decide(feedURL: feed), .refused(.feedNotConfigured),
        "\(feed ?? "nil") must not be accepted as an update feed")
    }
    XCTAssertTrue(UpdatePolicy.isUsableFeedURL(Self.shippingFeed))
  }

  // MARK: - Download and relaunch contract

  func testUpdatesDownloadAutomaticallyButInstallationRequiresRelaunchApproval() {
    XCTAssertTrue(UpdatePolicy.automaticallyDownloadsUpdates)
    XCTAssertTrue(UpdatePolicy.requiresRelaunchConfirmation)
  }

  func testDownloadedUpdateExposesAnExplicitRelaunchRequiredStateAndMessage() {
    XCTAssertEqual(UpdatePolicy.RelaunchState.idle.message, nil)
    let state = UpdatePolicy.RelaunchState.required(version: "1.1.0")
    XCTAssertEqual(
      state.message,
      "Context for Claude update 1.1.0 is downloaded and verified. Choose Install and Relaunch to apply it.")
    XCTAssertTrue(UpdatePolicy.relaunchPromptMessage(for: "1.1.0").contains("Install and relaunch"))
    XCTAssertTrue(UpdatePolicy.relaunchPromptMessage(for: "1.1.0").contains("capture"))
  }

  // MARK: - Airgap Mode

  /// Airgap Mode covers the updater like every other remote client. `AirgapEgressTests` already
  /// proves this over `Client.allCases`, which is what makes the coverage automatic; this names the
  /// update check specifically, because it is the client most easily argued into an exception —
  /// "it's only a version number" — and the argument is wrong. A scheduled request every six hours
  /// tells a third party that this app is installed here and which build is running.
  func testAirgapModeStopsTheUpdateCheckAndSaysWhere() {
    XCTAssertTrue(NetworkEgress.isSuppressed(.updateCheck, airgapMode: true))
    XCTAssertFalse(NetworkEgress.isSuppressed(.updateCheck, airgapMode: false))

    let sentence = NetworkEgress.explanation(.updateCheck)
    XCTAssertTrue(sentence.contains("Airgap Mode"), sentence)
    XCTAssertTrue(sentence.contains("Settings"), sentence)
  }

  /// **The regression test for a check and its download being guarded as one thing.**
  ///
  /// `automaticallyDownloadsUpdates` is true, so an allowed check runs straight on into a release-
  /// notes fetch and an archive download with no second question asked. Only the *check* was gated,
  /// so Airgap Mode turned on while the appcast was in flight still pulled tens of megabytes from a
  /// host the user had just told this app to stop talking to.
  ///
  /// Written over `Step.allCases` rather than as a list, for the same reason `AirgapEgressTests` is
  /// written over `Client.allCases`: a step added later is covered the moment it names itself.
  func testEverySparkleStepReReadsAirgapModeForItselfRatherThanInheritingTheCheck() {
    let recorder = AirgapSuppressionRecorder()
    defer { recorder.stop() }

    for step in UpdateEgress.Step.allCases {
      XCTAssertFalse(
        UpdateEgress.permits(step, isSuppressed: { true }),
        "\(step.rawValue) must not reach the network under Airgap Mode")
    }
    XCTAssertEqual(
      recorder.records.count, UpdateEgress.Step.allCases.count,
      "each refused step reports its own suppression, or the telemetry undercounts what was stopped")
    XCTAssertTrue(recorder.records.allSatisfy { $0.client == .updateCheck })

    for step in UpdateEgress.Step.allCases {
      XCTAssertTrue(
        UpdateEgress.permits(step, isSuppressed: { false }),
        "\(step.rawValue) must be unaffected when Airgap Mode is off")
    }
    XCTAssertEqual(
      recorder.records.count, UpdateEgress.Step.allCases.count, "and nothing more is reported")
  }

  /// The gates above are only real if Sparkle actually calls them, and `SPUUpdaterDelegate` is an
  /// all-optional protocol dispatched through `-respondsToSelector:`. A guard written for a callback
  /// the delegate does not implement looks exactly like a guard that works — which is precisely how
  /// the download went ungated for as long as the file existed.
  ///
  /// So this asks the ObjC runtime the same question Sparkle asks, of the real production class.
  /// The selectors carry a trailing `error:` where the Swift method `throws`.
  func testTheDelegateSparkleTalksToActuallyImplementsEachGatedCallback() {
    let gated = [
      "updater:mayPerformUpdateCheck:error:",
      "updater:shouldDownloadReleaseNotesForUpdate:",
      "updater:shouldProceedWithUpdate:updateCheck:error:",
    ]
    for name in gated {
      XCTAssertTrue(
        UpdaterEvents.instancesRespond(to: NSSelectorFromString(name)),
        "Sparkle asks for \(name) and would go ahead unguarded if it is not answered")
    }
  }

  /// A refusal Sparkle surfaces has to be the same sentence the Settings row shows, or a person
  /// meets two different explanations for one switch.
  func testTheErrorSparkleIsThrownCarriesTheSentenceTheSettingsRowShows() {
    XCTAssertEqual(
      UpdateEgress.refusal.localizedDescription, NetworkEgress.explanation(.updateCheck))
  }

  // MARK: - What the next launch is told

  /// The note the outgoing build leaves so the incoming one can tell "I was just updated" from "I
  /// was just installed" — the only two states that look identical and mean opposite things when a
  /// capture permission is missing.
  func testAnUpdateLeavesARecordTheNextLaunchCanRead() {
    let defaults = throwawayDefaults()
    UpdateRelaunch.note(installOf: "1.1.0", from: "1.0.0", defaults: defaults)

    let record = UpdateRelaunch.consume(currentVersion: "1.1.0", defaults: defaults)
    XCTAssertEqual(record?.fromVersion, "1.0.0")
    XCTAssertEqual(record?.toVersion, "1.1.0")
  }

  /// Read once. A record that survives its own launch eventually fires against an unrelated one,
  /// and "your permissions were reset by an update" shown a week after the update is worse than
  /// silence — it sends the user to re-grant something that was never revoked.
  func testTheRecordIsConsumedRatherThanLeftBehind() {
    let defaults = throwawayDefaults()
    UpdateRelaunch.note(installOf: "1.1.0", from: "1.0.0", defaults: defaults)

    XCTAssertNotNil(UpdateRelaunch.consume(currentVersion: "1.1.0", defaults: defaults))
    XCTAssertNil(UpdateRelaunch.consume(currentVersion: "1.1.0", defaults: defaults))
  }

  /// An install that was announced and then did not happen — a failed download, a cancelled
  /// install, a user who quit first — comes back as the *same* version. Reporting that as an update
  /// would blame the updater for permissions it never touched. The stale note is still cleared,
  /// because a note that is not cleared is a note that fires later.
  func testAnAnnouncedInstallThatNeverHappenedIsNotReportedAsAnUpdate() {
    let defaults = throwawayDefaults()
    UpdateRelaunch.note(installOf: "1.1.0", from: "1.0.0", defaults: defaults)

    XCTAssertNil(
      UpdateRelaunch.consume(currentVersion: "1.0.0", defaults: defaults),
      "the version did not change, so nothing was installed")
    XCTAssertNil(defaults.string(forKey: UpdateRelaunch.fromVersionKey))
  }

  func testALaunchWithNoRecordReportsNothing() {
    XCTAssertNil(UpdateRelaunch.consume(currentVersion: "1.0.0", defaults: throwawayDefaults()))
  }

  /// The sentence a user reads when capture stopped across an update has to name the update as the
  /// cause and say where to fix it. Without the first half it reads as the app being broken;
  /// without the second there is nothing to do about it.
  func testTheLostPermissionsSentenceNamesTheUpdateAndWhereToFixIt() {
    let record = UpdateRelaunch.Record(
      fromVersion: "1.0.0", toVersion: "1.1.0", notedAt: Date())
    let sentence = UpdateRelaunch.permissionsLostMessage(record)
    XCTAssertTrue(sentence.contains("1.1.0"), sentence)
    XCTAssertTrue(sentence.contains("System Settings"), sentence)
  }

  // MARK: - The shipped Info.plist

  /// A **static tripwire**, not behavioural coverage: it reads `Resources/Info.plist` off disk and
  /// checks that the keys the policy asks about are the keys the bundle actually carries. It cannot
  /// prove the updater works. It can prove the two halves have not drifted apart — a renamed key
  /// would otherwise disable updates silently in a shipping build, and there is no other cheap
  /// place that notices.
  func testTheShippedPlistCarriesTheKeysThePolicyReadsAndNoPrivateKey() throws {
    let plistURL = URL(fileURLWithPath: #filePath)  // Tests/ContextAppTests/UpdatePolicyTests.swift
      .deletingLastPathComponent()  // Tests/ContextAppTests
      .deletingLastPathComponent()  // Tests
      .deletingLastPathComponent()  // package root
      .appendingPathComponent("Resources/Info.plist")
    let plist =
      try PropertyListSerialization.propertyList(
        from: Data(contentsOf: plistURL), format: nil) as? [String: Any]
    let values = try XCTUnwrap(plist)

    XCTAssertEqual(
      values["CFBundleIdentifier"] as? String, UpdatePolicy.shippingBundleIdentifier,
      "the policy's shipping identifier and the plist's must be the same string")
    XCTAssertTrue(
      UpdatePolicy.isUsableFeedURL(values["SUFeedURL"] as? String),
      "SUFeedURL must be the HTTPS product-scoped Context release feed")
    XCTAssertEqual(values["SUFeedURL"] as? String, UpdatePolicy.releaseFeedURL)
    XCTAssertEqual(values["SUEnableAutomaticChecks"] as? Bool, true)
    XCTAssertEqual(values["SUAutomaticallyUpdate"] as? Bool, true)

    // The public key is expected to still be the placeholder in the repository. That is the
    // point: a *private* key must never be committed, and the public one is filled in by the
    // releasing maintainer at release time (docs/releasing.md). What this asserts is the pairing
    // — placeholder in the plist means the updater is off, a real key means it is on — so neither
    // can be changed without the other being considered.
    let shippedKey = values["SUPublicEDKey"] as? String
    XCTAssertNotNil(shippedKey, "SUPublicEDKey must be present even while it is a placeholder")
    XCTAssertEqual(
      UpdatePolicy.isConfiguredPublicKey(shippedKey),
      shippedKey != UpdatePolicy.publicKeyPlaceholder,
      "a value that is not the placeholder must be a usable key, and vice versa")
  }

  // MARK: - Helpers

  /// A throwaway `UserDefaults` suite, so a test never moves the developer's own update state.
  private func throwawayDefaults() -> UserDefaults {
    let suiteName = "update-policy-tests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName) ?? .standard
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    return defaults
  }
}
