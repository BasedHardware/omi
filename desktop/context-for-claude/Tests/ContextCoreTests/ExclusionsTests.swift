import Foundation
import XCTest

@testable import ContextCore

/// Observer callbacks are `@Sendable`, so what they write into has to be too.
private final class Counts: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Int] = []

    func record(_ value: Int) {
        lock.lock()
        storage.append(value)
        lock.unlock()
    }

    var values: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }
}

/// The privacy engine, and the one place in this app where a bug is a breach rather than a gap.
///
/// Everything else here can be wrong and cost the user a search result. An exclusion that fails
/// costs them a plaintext, searchable, model-readable copy of a password vault, a bank balance, or a
/// private tab — permanently, because nothing in this database expires text and nothing un-tells a
/// model what it was given. So these tests are written the other way round from the rest of the
/// suite: they assert what must *never* be captured first, and only then that ordinary windows still
/// are.
final class ExclusionsTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("exclusions-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    /// An engine whose entire world is the temp directory. Never `ExclusionEngine.shared`: these
    /// tests must not read, write, or create anything in the user's real support directory.
    private func makeEngine(file: String = "exclusions.json") -> ExclusionEngine {
        ExclusionEngine(
            configurationURL: root.appendingPathComponent(file),
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
    }

    private func write(_ contents: String, to file: String = "exclusions.json") throws {
        try contents.write(
            to: root.appendingPathComponent(file), atomically: true, encoding: .utf8)
    }

    private func chrome(title: String? = nil, url: String? = nil) -> CaptureSubject {
        CaptureSubject(
            bundleID: "com.google.Chrome", appName: "Google Chrome", windowTitle: title, url: url)
    }

    // MARK: - 1. Default-excluded before any user action

    /// The requirement in its strongest form: a Mac that has never seen this app, with no
    /// configuration written and nobody having clicked anything, already refuses password managers
    /// and the login screen.
    func testAFreshInstallExcludesPasswordManagersBeforeAnyUserAction() {
        let engine = makeEngine()

        XCTAssertEqual(engine.health, .defaultsOnly, "no configuration exists yet, and that is fine")
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: root.appendingPathComponent("exclusions.json").path),
            "constructing the engine must not need to write anything to be safe")

        for app in ExclusionCatalog.lockedApps {
            let subject = CaptureSubject(bundleID: app.bundleID, appName: app.displayName)
            XCTAssertNotNil(
                engine.exclusionReason(for: subject),
                "\(app.displayName) was capturable on a fresh install")
            XCTAssertEqual(engine.state(ofBundleID: app.bundleID), .lockedExcluded)
        }

        // The two the reference shows in the locked state, named explicitly so a future edit to the
        // catalog cannot quietly drop them.
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.apple.keychainaccess")))
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.apple.Passwords")))
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.apple.loginwindow")))
    }

    /// The legacy principal: an installation that predates this feature entirely. Every user today
    /// is this case — no `exclusions.json`, no migration, no prompt — and a new fail-closed gate
    /// that breaks or ignores them is the failure mode this test exists to prevent.
    ///
    /// Two things are asserted, and both matter: the safe defaults are *in force*, and they are
    /// defaults rather than a panic — an ordinary window is still captured, so the gate has not
    /// simply shut the product off for existing users.
    func testLegacyInstallationWithNoConfigurationGetsTheSafeDefaults() {
        let engine = makeEngine()

        XCTAssertEqual(engine.health, .defaultsOnly)
        XCTAssertNotNil(
            engine.exclusionReason(for: CaptureSubject(bundleID: "com.1password.1password")),
            "an existing install with no configuration must not be an allow-everything set")
        XCTAssertTrue(
            engine.current.categories.contains(.passwordManagers),
            "the Password Managers category is ticked before the user has seen the pane")
        XCTAssertTrue(
            engine.current.excludePrivateBrowsing,
            "Exclude Private Tabs is checked in the reference, so it is on by default")
        XCTAssertTrue(
            engine.current.lockedApps.contains("com.apple.keychainaccess"),
            "the locked set is never empty, whatever the configuration says")

        // …and the product still works for them.
        XCTAssertNil(
            engine.exclusionReason(
                for: CaptureSubject(
                    bundleID: "com.apple.Notes", appName: "Notes", windowTitle: "Groceries")),
            "safe defaults must not mean capturing nothing")
    }

    func testLockedDefaultsCannotBeRemovedByTheUser() {
        let engine = makeEngine()

        XCTAssertEqual(
            engine.setExcluded(false, bundleID: "com.apple.keychainaccess"), .refusedLocked,
            "the reference shows this checkbox in a state the user cannot clear")
        XCTAssertEqual(engine.setExcluded(false, bundleID: "com.1password.1password"), .refusedLocked)
        XCTAssertEqual(engine.setExcluded(false, bundleID: "com.apple.loginwindow"), .refusedLocked)

        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.apple.keychainaccess")))
        XCTAssertEqual(engine.state(ofBundleID: "com.1password.1password"), .lockedExcluded)
        XCTAssertTrue(engine.snapshot().excludedApps.first?.isLocked ?? false)
    }

    // MARK: - 2. Bundle identifiers, not display names

    func testAppExclusionsAreKeyedByBundleIdentifierNotDisplayName() {
        let engine = makeEngine()
        XCTAssertEqual(
            engine.setExcluded(true, bundleID: "com.tinyspeck.slackmacgap", displayName: "Slack"),
            .applied)

        // Renaming the app does not lift the exclusion: the identity is the bundle id.
        XCTAssertNotNil(
            engine.exclusionReason(
                for: CaptureSubject(bundleID: "com.tinyspeck.slackmacgap", appName: "Totally Fine")))

        // A different app that calls itself Slack is *also* refused, because a display name can only
        // ever widen the net. The asymmetry is the whole design: names add exclusions, never remove.
        XCTAssertNotNil(
            engine.exclusionReason(for: CaptureSubject(bundleID: "com.evil.imposter", appName: "Slack")))

        // But a name that merely contains an excluded one is not a match.
        XCTAssertNil(
            engine.exclusionReason(
                for: CaptureSubject(bundleID: "com.other.app", appName: "Slackline Notes")))
    }

    /// Helper processes are where the secret is actually on screen — 1Password's autofill popover is
    /// drawn by a different bundle than the app — so an exclusion covers an identifier's children.
    /// At a dot boundary only, or excluding one vendor's app would exclude another's.
    func testExcludingAnAppCoversItsHelpersButNotALookalikeIdentifier() {
        let engine = makeEngine()
        engine.setExcluded(true, bundleID: "com.acme.vault", displayName: "Vault")

        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acme.vault")))
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acme.vault.helper")))
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "COM.ACME.VAULT")))

        XCTAssertNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acme.vaultx")))
        XCTAssertNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acme.vault-evil")))
        XCTAssertNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acmevault")))
    }

    func testThePasswordManagerCategoryExpandsToRealBundleIdentifiers() {
        let members = ExclusionCatalog.apps(in: .passwordManagers)

        XCTAssertGreaterThanOrEqual(members.count, 10, "one tick has to actually cover the category")
        for expected in [
            "com.1password.1password", "com.bitwarden.desktop", "com.apple.keychainaccess",
            "com.apple.Passwords", "org.keepassxc.keepassxc",
        ] {
            XCTAssertTrue(
                members.contains { $0.bundleID == expected }, "\(expected) missing from the category")
        }
        for member in members {
            XCTAssertTrue(
                member.bundleID.contains("."),
                "\(member.bundleID) is not a bundle identifier — names are not identities")
            XCTAssertTrue(
                ExclusionCatalog.lockedBundleIdentifiers.contains(member.foldedBundleID),
                "every password manager in the category is also locked by default")
        }
    }

    func testTickingACategoryExcludesEveryMemberAndUntickingRestoresThem() {
        let engine = makeEngine()
        let subject = chrome(url: "https://online.chase.com/accounts")

        XCTAssertNil(engine.exclusionReason(for: subject), "Banks is off by default")

        XCTAssertEqual(engine.setCategory(.banks, excluded: true), .applied)
        XCTAssertNotNil(engine.exclusionReason(for: subject))
        XCTAssertNotNil(engine.exclusionReason(for: chrome(url: "https://barclays.co.uk")))
        XCTAssertNotNil(engine.exclusionReason(for: chrome(url: "https://www.monzo.com/login")))

        XCTAssertEqual(engine.setCategory(.banks, excluded: false), .applied)
        XCTAssertNil(engine.exclusionReason(for: subject))
    }

    // MARK: - 3. Website matching, and the adversarial cases

    func testSubdomainsOfAnExcludedDomainAreExcluded() {
        let engine = makeEngine()
        XCTAssertNotNil(engine.excludeWebsite("example.com"))

        for host in [
            "example.com",
            "www.example.com",
            "login.example.com",
            "a.b.deeply.nested.example.com",
            "EXAMPLE.COM",
            "example.com.",  // fully-qualified: the same host
            "example.com:8443",
            "https://login.example.com/path?q=1#frag",
            "http://user:hunter2@www.example.com/",
            "//example.com/x",
        ] {
            XCTAssertNotNil(
                engine.exclusionReason(for: chrome(url: host)),
                "\(host) is the excluded site and was captured")
        }
    }

    /// The leak a naive check ships. `contains` lets an attacker choose `example.com.evil.net`;
    /// `hasSuffix` without the dot matches `notexample.com`. Both are asserted here directly rather
    /// than only through the engine, because this is the rule and not a consequence of one.
    func testLookalikeDomainsAreNotExcluded() {
        let engine = makeEngine()
        XCTAssertNotNil(engine.excludeWebsite("example.com"))

        for host in [
            "notexample.com",
            "example.com.evil.net",
            "https://example.com.evil.net/login",
            "myexample.com",
            "example.co",
            "example.company.com",
            "examplecom",
            "exampleXcom",
            "https://evil.net/example.com",
            "https://evil.net/?next=https://example.com",
        ] {
            XCTAssertNil(
                engine.exclusionReason(for: chrome(url: host)),
                "\(host) is a different site and lost its frame")
        }

        // The rule, stated without the engine in the way.
        XCTAssertFalse(DomainMatcher.matches(pattern: "example.com", candidate: "notexample.com"))
        XCTAssertFalse(DomainMatcher.matches(pattern: "example.com", candidate: "example.com.evil.net"))
        XCTAssertTrue("example.com.evil.net".contains("example.com"), "…which is why contains is wrong")
        XCTAssertTrue("notexample.com".hasSuffix("example.com"), "…and why a bare hasSuffix is wrong")
        XCTAssertTrue(DomainMatcher.matches(pattern: "example.com", candidate: "login.example.com"))
    }

    /// A subdomain pattern is not a shortcut for its parent: excluding `www.example.com` hides that
    /// host and its own children, and says nothing about `example.com`.
    func testASubdomainPatternDoesNotExcludeItsParent() {
        let engine = makeEngine()
        engine.excludeWebsite("www.example.com")

        XCTAssertNotNil(engine.exclusionReason(for: chrome(url: "https://www.example.com/x")))
        XCTAssertNotNil(engine.exclusionReason(for: chrome(url: "https://a.www.example.com/x")))
        XCTAssertNil(engine.exclusionReason(for: chrome(url: "https://example.com/x")))
        XCTAssertNil(engine.exclusionReason(for: chrome(url: "https://login.example.com/x")))
    }

    func testDomainNormalisationHandlesWhatUsersActuallyPaste() {
        XCTAssertEqual(DomainPattern("  Example.COM  ")?.host, "example.com")
        XCTAssertEqual(DomainPattern("https://www.example.com/path?a=b#c")?.host, "www.example.com")
        XCTAssertEqual(DomainPattern("*.example.com")?.host, "example.com")
        XCTAssertEqual(DomainPattern("example.com.")?.host, "example.com")
        XCTAssertEqual(DomainPattern("example.com:8443")?.host, "example.com")
        XCTAssertEqual(DomainPattern("user:pw@example.com")?.host, "example.com")
        XCTAssertEqual(DomainPattern("http://[::1]:8080/x")?.host, "[::1]")
        XCTAssertEqual(DomainPattern("münchen.de")?.host, "münchen.de")
    }

    /// A pattern that cannot match anything is worse than a rejected keystroke: the row appears in
    /// the list, the user believes the site is hidden, and it is not.
    func testInputThatIsNotAHostIsRejectedRatherThanStored() {
        for junk in ["", "   ", "not a domain", "..", "*", ".", "://", "\"example.com\"", "a b.com"] {
            XCTAssertNil(DomainPattern(junk), "\(junk.debugDescription) was accepted as a domain")
        }

        let engine = makeEngine()
        XCTAssertNil(engine.excludeWebsite("not a domain"))
        XCTAssertTrue(engine.current.websites.isEmpty)
    }

    /// A browser title that names an excluded domain counts — but almost none ever does, and that
    /// limit is asserted here rather than left to be discovered in a database.
    ///
    /// This test used to stop at the first assertion, with a title of `Barclays | barclays.co.uk`.
    /// It passed, and it protected nobody: that shape occurs **0 times in 955 real browser frames**
    /// on this machine, because a browser titles its window with the page title. The title tier is
    /// real and cheap and stays; what it is not is the thing standing between a user and their bank.
    /// `CaptureAddressTests` covers the tier that is.
    func testABrowserTitleNamingAnExcludedDomainIsRefusedButAlmostNoRealTitleDoes() {
        let engine = makeEngine()
        engine.setCategory(.banks, excluded: true)

        XCTAssertNotNil(
            engine.exclusionReason(for: chrome(title: "Barclays | barclays.co.uk")),
            "a browser window naming the bank must not be captured just because no URL was read")

        // What a browser really writes there. Arc titles its windows `LinkedIn`, `Anthropic`,
        // `Apple Inc.` — the page's own title, with no host in it anywhere.
        XCTAssertNil(
            engine.exclusionReason(for: chrome(title: "Barclays")),
            "a page title is not a host, and pretending otherwise is what made this control a "
                + "decoration for as long as the title was the only evidence")

        XCTAssertNil(
            engine.exclusionReason(
                for: CaptureSubject(
                    bundleID: "com.apple.dt.Xcode", appName: "Xcode",
                    windowTitle: "barclays.co.uk.swift")),
            "a filename in an editor is not a website")
        XCTAssertNil(
            engine.exclusionReason(for: chrome(title: "Flight deals to Lisbon")),
            "an ordinary browser window is still captured")
    }

    func testExcludePrivateTabsWorksAcrossBrowsersAndIsOnByDefault() {
        let engine = makeEngine()
        XCTAssertTrue(engine.current.excludePrivateBrowsing)

        let privateWindows = [
            CaptureSubject(
                bundleID: "com.google.Chrome", appName: "Google Chrome",
                windowTitle: "New Tab - Google Chrome (Incognito)"),
            CaptureSubject(
                bundleID: "org.mozilla.firefox", appName: "Firefox",
                windowTitle: "Mozilla Firefox Private Browsing"),
            CaptureSubject(
                bundleID: "com.microsoft.edgemac", appName: "Microsoft Edge",
                windowTitle: "Start [InPrivate]"),
            CaptureSubject(
                bundleID: "com.apple.Safari", appName: "Safari", windowTitle: "Reading",
                privacy: .privateBrowsing),
        ]
        for window in privateWindows {
            XCTAssertEqual(
                engine.exclusionReason(for: window), .privateBrowsing,
                "a private window was captured: \(window.appName ?? "?")")
        }

        engine.setExcludePrivateBrowsing(false)
        for window in privateWindows {
            XCTAssertNil(engine.exclusionReason(for: window))
        }
    }

    /// The named hole, asserted so it cannot be mistaken for working. Safari marks a private window
    /// nowhere in its title, so the core cannot classify one from a title alone — the app has to
    /// supply the evidence, and this test is what says so out loud.
    func testSafariPrivateWindowsCannotBeClassifiedFromTheTitleAlone() {
        let engine = makeEngine()
        let unmarked = CaptureSubject(
            bundleID: "com.apple.Safari", appName: "Safari", windowTitle: "Lisbon in November")

        XCTAssertEqual(engine.current.effectivePrivacy(of: unmarked), .unknown)
        XCTAssertNil(
            engine.exclusionReason(for: unmarked),
            "refusing every window we cannot classify would mean refusing all browsing")

        var informed = unmarked
        informed.privacy = .privateBrowsing
        XCTAssertEqual(engine.exclusionReason(for: informed), .privateBrowsing)
    }

    // MARK: - 4. Immediate effect, including in-flight work

    func testAnExclusionTakesEffectOnTheNextCaptureWithNoRelaunch() {
        let engine = makeEngine()
        let subject = CaptureSubject(bundleID: "com.tinyspeck.slackmacgap", appName: "Slack")

        XCTAssertNil(engine.exclusionReason(for: subject))
        engine.setExcluded(true, bundleID: "com.tinyspeck.slackmacgap", displayName: "Slack")
        XCTAssertNotNil(
            engine.exclusionReason(for: subject), "an exclusion that waits for a relaunch is not one")
    }

    /// The in-flight requirement. A frame captured before the click and written after it must be
    /// dropped, which is only possible because the ticket carries the generation that admitted it.
    func testAFrameQueuedBeforeTheExclusionIsDroppedAtTheWriteBarrier() throws {
        let engine = makeEngine()
        let subject = CaptureSubject(bundleID: "com.tinyspeck.slackmacgap", appName: "Slack")

        let ticket = try XCTUnwrap(engine.admit(subject).ticket)
        XCTAssertNil(engine.revalidate(ticket), "nothing has changed yet")

        engine.setExcluded(true, bundleID: "com.tinyspeck.slackmacgap", displayName: "Slack")

        XCTAssertEqual(
            engine.revalidate(ticket), .userExcludedApp(bundleID: "com.tinyspeck.slackmacgap"),
            "a queued-but-unwritten frame must still be refusable")
    }

    func testExcludingADomainDropsAFrameAlreadyQueuedFromThatDomain() throws {
        let engine = makeEngine()
        let ticket = try XCTUnwrap(engine.admit(chrome(url: "https://login.example.com/pay")).ticket)

        engine.excludeWebsite("example.com")

        XCTAssertEqual(engine.revalidate(ticket), .excludedWebsite(pattern: "example.com"))
    }

    /// Un-excluding must also take effect immediately, or the pane lies in the other direction.
    func testRemovingAnExclusionReadmitsAQueuedFrame() throws {
        let engine = makeEngine()
        engine.setExcluded(true, bundleID: "com.tinyspeck.slackmacgap", displayName: "Slack")
        let ticket = try XCTUnwrap(
            engine.admit(CaptureSubject(bundleID: "com.other.app", appName: "Other")).ticket)

        engine.setExcluded(false, bundleID: "com.tinyspeck.slackmacgap")

        XCTAssertNil(engine.revalidate(ticket))
    }

    /// A ticket cannot be minted for a refused capture, which is what makes "everything queued was
    /// vetted" a property of the type rather than a habit of the caller.
    func testARefusedCaptureYieldsNoTicket() {
        let engine = makeEngine()

        let admission = engine.admit(CaptureSubject(bundleID: "com.apple.keychainaccess"))

        XCTAssertNil(admission.ticket)
        XCTAssertEqual(admission.reason, .defaultExcludedApp(bundleID: "com.apple.keychainaccess"))
    }

    /// The barrier a caller with only a `Frame` in hand can still use: it stores `appName` and a
    /// title, and no bundle identifier at all.
    func testTheWriteBarrierRefusesAPasswordManagerFromItsDisplayNameAlone() {
        let engine = makeEngine()

        XCTAssertNotNil(engine.shouldDropQueuedFrame(appName: "1Password", windowTitle: "Personal"))
        XCTAssertNotNil(engine.shouldDropQueuedFrame(appName: "Keychain Access", windowTitle: nil))

        engine.setExcluded(true, bundleID: "com.tinyspeck.slackmacgap", displayName: "Slack")
        XCTAssertNotNil(engine.shouldDropQueuedFrame(appName: "Slack", windowTitle: "general"))
        XCTAssertNil(engine.shouldDropQueuedFrame(appName: "Notes", windowTitle: "Groceries"))
    }

    /// A dropped frame's image must go with it. `ScreenPipeline` writes the HEIC before any row
    /// exists and pruning walks the `frames` table, so a file left behind here is a screenshot of an
    /// excluded window that nothing will ever delete.
    func testDiscardingAnExcludedFrameUnlinksItsImage() throws {
        let engine = makeEngine()
        let frames = root.appendingPathComponent("Frames", isDirectory: true)
        try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
        let image = frames.appendingPathComponent("frame_010101_000.heic")
        try Data([0x00]).write(to: image)

        engine.discard(
            Frame(capturedAt: 1, appName: "1Password", imagePath: image.path),
            reason: .defaultExcludedApp(bundleID: "com.1password.1password"))

        XCTAssertFalse(
            FileManager.default.fileExists(atPath: image.path),
            "the screenshot of an excluded window outlived the row that was refused")
    }

    func testDiscardRefusesToUnlinkOutsideTheFramesDirectory() throws {
        let engine = makeEngine()
        let outsider = root.appendingPathComponent("not-a-frame.heic")
        try Data([0x00]).write(to: outsider)

        engine.discard(
            Frame(capturedAt: 1, imagePath: outsider.path), reason: .privateBrowsing)

        XCTAssertTrue(
            FileManager.default.fileExists(atPath: outsider.path),
            "a refusal is not a licence to delete an arbitrary path")
    }

    // MARK: - 5. Airgap Mode and favicons

    /// Airgap Mode promises to suppress remote favicon requests. A UI that hides an image it already
    /// fetched has not kept that promise, so the decision is made here and the URL is handed out.
    func testAirgapModeSuppressesTheFaviconRequestItself() {
        let engine = makeEngine()

        XCTAssertEqual(
            engine.faviconFetch(for: "example.com"),
            .allowed(URL(string: "https://example.com/favicon.ico")!))
        XCTAssertTrue(engine.isFaviconFetchAllowed)

        engine.setAirgapMode(true)

        XCTAssertEqual(engine.faviconFetch(for: "example.com"), .suppressed(.airgapMode))
        XCTAssertFalse(engine.isFaviconFetchAllowed)
        XCTAssertFalse(engine.snapshot().isFaviconFetchAllowed)
    }

    /// The favicon URL is always the domain's own. A third-party favicon service would tell someone
    /// else every domain the user chose to hide, which is the opposite of what this pane is for.
    func testFaviconRequestsGoToTheDomainItselfAndNowhereElse() throws {
        let engine = makeEngine()

        let url = try XCTUnwrap(engine.faviconFetch(for: "https://login.example.com/x").url)

        XCTAssertEqual(url.host, "login.example.com")
        XCTAssertEqual(url.scheme, "https")
        XCTAssertEqual(url.path, "/favicon.ico")
        XCTAssertEqual(engine.faviconFetch(for: "not a host"), .suppressed(.notAHost))
    }

    // MARK: - 6. Fail closed, and prove it

    /// The test the requirement asks for by name: a corrupt configuration must not silently start
    /// capturing password managers.
    func testACorruptConfigurationDoesNotStartCapturingPasswordManagers() throws {
        try write("{ this is not json")
        let engine = makeEngine()

        guard case .failedClosed(.malformed) = engine.health else {
            return XCTFail("a corrupt configuration must be recognised as one: \(engine.health)")
        }
        XCTAssertNotNil(
            engine.exclusionReason(for: CaptureSubject(bundleID: "com.1password.1password")),
            "a corrupt file must never be a reason to capture a password vault")
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.apple.keychainaccess")))

        // "More is excluded, never less": every category on, private tabs on, network off.
        XCTAssertEqual(engine.current.categories, Set(ExclusionCategory.allCases))
        XCTAssertNotNil(
            engine.exclusionReason(for: chrome(url: "https://chase.com")),
            "the Banks category is forced on when the configuration cannot be trusted")
        XCTAssertTrue(engine.current.excludePrivateBrowsing)
        XCTAssertEqual(engine.faviconFetch(for: "example.com"), .suppressed(.configurationUnavailable))
    }

    func testEveryUnreadableShapeOfConfigurationFailsClosed() throws {
        let cases: [(name: String, contents: String)] = [
            ("empty.json", ""),
            ("truncated.json", "{\"version\":1,\"excludedDomains\":[\"exa"),
            ("wrong-types.json", "{\"excludedDomains\": 7}"),
            ("not-an-object.json", "[\"example.com\"]"),
            ("html.json", "<!doctype html><html>error</html>"),
        ]

        for (name, contents) in cases {
            try write(contents, to: name)
            let engine = makeEngine(file: name)

            XCTAssertTrue(
                engine.health.isFailClosed, "\(name) was accepted as a configuration")
            XCTAssertNotNil(
                engine.exclusionReason(for: CaptureSubject(bundleID: "com.apple.Passwords")),
                "\(name) left Apple Passwords capturable")
            XCTAssertTrue(engine.current.categories.contains(.banks), "\(name) did not fail closed")
        }
    }

    /// A file this build cannot open at all — a directory in its place stands in for permissions and
    /// I/O errors, which cannot be produced portably in a test.
    func testAConfigurationThatCannotBeReadAtAllFailsClosed() throws {
        let path = root.appendingPathComponent("exclusions.json")
        try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true)

        let engine = makeEngine()

        guard case .failedClosed(.unreadable) = engine.health else {
            return XCTFail("an unreadable configuration must fail closed: \(engine.health)")
        }
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.bitwarden.desktop")))
    }

    /// A file from a newer build may carry exclusions this one cannot express. Everything decoded is
    /// still honoured — forgetting the user's own list is the one direction this must never move in —
    /// and the unknown remainder is covered by failing closed.
    func testAConfigurationFromANewerBuildKeepsItsListsAndStillFailsClosed() throws {
        try write(
            """
            {"version": 99, "excludedDomains": ["example.com"],
             "excludedApps": [{"bundleID": "com.acme.app", "displayName": "Acme"}],
             "somethingThisBuildHasNeverHeardOf": true}
            """)
        let engine = makeEngine()

        XCTAssertEqual(engine.health, .failedClosed(.writtenByNewerVersion(99)))
        XCTAssertNotNil(engine.exclusionReason(for: chrome(url: "https://www.example.com")))
        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acme.app")))
        XCTAssertTrue(engine.current.categories.contains(.banks))
    }

    /// A capture admitted while the configuration was trustworthy, and written after it stopped
    /// being: what the user excluded is now unknown, so the frame goes. Dropping one frame is
    /// recoverable; writing one they excluded is not.
    func testACaptureAdmittedBeforeTheConfigurationWentBadIsDropped() throws {
        let engine = makeEngine()
        let ticket = try XCTUnwrap(
            engine.admit(CaptureSubject(bundleID: "com.apple.Notes", appName: "Notes")).ticket)

        try write("{ corrupt")
        engine.reload()

        XCTAssertEqual(engine.revalidate(ticket), .configurationUnavailable)
    }

    /// Failing closed must not destroy the evidence. The file is unreadable to *this* build, which is
    /// not the same as meaningless, so it is copied aside before anything replaces it — and the
    /// extra exclusions the fail-closed state implied are written down rather than evaporating on
    /// the first click.
    func testAnUnreadableConfigurationIsPreservedAndItsExtraExclusionsAreMaterialised() throws {
        let original = "{ this is not json"
        try write(original)
        let engine = makeEngine()

        engine.excludeWebsite("example.com")

        let backup = root.appendingPathComponent("exclusions.json.unreadable")
        XCTAssertEqual(try String(contentsOf: backup, encoding: .utf8), original)
        XCTAssertEqual(engine.health, .configured)

        // A second engine on the same file — the relaunch. The forced categories survived it.
        let relaunched = makeEngine()
        XCTAssertEqual(relaunched.health, .configured)
        XCTAssertTrue(relaunched.current.categories.contains(.banks))
        XCTAssertTrue(relaunched.current.excludePrivateBrowsing)
        XCTAssertNotNil(relaunched.exclusionReason(for: chrome(url: "https://login.example.com")))
    }

    // MARK: - Persistence

    func testExclusionsSurviveARelaunch() {
        let engine = makeEngine()
        engine.setExcluded(true, bundleID: "com.tinyspeck.slackmacgap", displayName: "Slack")
        engine.excludeWebsite("https://www.example.com/settings")
        engine.setCategory(.banks, excluded: true)
        engine.setAirgapMode(true)

        let relaunched = makeEngine()

        XCTAssertEqual(relaunched.health, .configured)
        XCTAssertNotNil(
            relaunched.exclusionReason(for: CaptureSubject(bundleID: "com.tinyspeck.slackmacgap")))
        XCTAssertNotNil(relaunched.exclusionReason(for: chrome(url: "https://www.example.com")))
        XCTAssertNotNil(relaunched.exclusionReason(for: chrome(url: "https://chase.com")))
        XCTAssertFalse(relaunched.isFaviconFetchAllowed)
    }

    /// The stored file holds the user's choices and nothing else. What is not written down cannot be
    /// edited out, which is why no hand-edit can produce a configuration where password managers are
    /// capturable.
    func testTheDefaultExcludedSetIsNeverWrittenToDiskWhereItCouldBeEditedOut() throws {
        let engine = makeEngine()
        engine.setExcluded(true, bundleID: "com.acme.app", displayName: "Acme")

        let saved = try String(
            contentsOf: root.appendingPathComponent("exclusions.json"), encoding: .utf8)

        XCTAssertFalse(saved.contains("keychainaccess"))
        XCTAssertFalse(saved.contains("1password"))
        XCTAssertTrue(saved.contains("com.acme.app"))
    }

    /// A save that fails must not undo the exclusion — it is in force now, which is the half that
    /// matters — and must not claim to have persisted it.
    func testAFailedSaveKeepsTheExclusionLiveAndReportsThatItWasNotPersisted() {
        let engine = ExclusionEngine(
            configurationURL: URL(fileURLWithPath: "/dev/null/nowhere/exclusions.json"),
            framesRoot: root)

        engine.setExcluded(true, bundleID: "com.acme.app", displayName: "Acme")

        XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: "com.acme.app")))
        guard case .notPersisted = engine.health else {
            return XCTFail("a failed save must be reported, not swallowed: \(engine.health)")
        }
    }

    // MARK: - 7. One decision path, not two

    /// The integration requirement: `Redaction` and the exclusions engine agree about the default
    /// set because there is only one list. A second copy is how a locked checkbox comes to mean
    /// nothing.
    func testRedactionAndTheExclusionEngineShareOneDefaultExcludedList() {
        let engine = makeEngine()

        for app in ExclusionCatalog.lockedApps {
            XCTAssertTrue(
                Redaction.isSensitiveWindow(app: app.bundleID, title: nil),
                "\(app.bundleID) is a locked exclusion but Redaction would read it")
            XCTAssertNotNil(engine.exclusionReason(for: CaptureSubject(bundleID: app.bundleID)))
        }
        for tool in ExclusionCatalog.screenCaptureTools {
            XCTAssertTrue(Redaction.isSensitiveWindow(app: tool.bundleID, title: nil))
        }
    }

    /// The pre-existing half of the gate still fires through the composed policy, and reports itself
    /// as what it is.
    func testCapturePolicyStillRefusesCredentialSurfacesTheUserNeverConfigured() {
        let sensitive = CaptureSubject(
            bundleID: "com.apple.Safari", appName: "Safari", windowTitle: "Sign in — Acme Bank")

        XCTAssertEqual(
            CapturePolicy.exclusion(for: sensitive, using: .safeDefaults), .credentialSurface)
        XCTAssertNil(
            CapturePolicy.exclusion(
                for: CaptureSubject(
                    bundleID: "com.apple.Safari", appName: "Safari",
                    windowTitle: "Flight deals to Lisbon"),
                using: .safeDefaults),
            "over-exclusion destroys the product just as surely as under-exclusion leaks it")
    }

    /// Reasons are logged. A window excluded *because of* its title or its domain is exactly the one
    /// whose title and domain must not be written to a log file.
    func testALoggedReasonNeverCarriesTheTitleOrTheDomain() {
        let engine = makeEngine()
        engine.excludeWebsite("secret-clinic.example")

        let reason = engine.exclusionReason(
            for: chrome(
                title: "Appointment — secret-clinic.example",
                url: "https://secret-clinic.example/x"))

        XCTAssertEqual(reason, .excludedWebsite(pattern: "secret-clinic.example"))
        XCTAssertFalse(reason?.logDescription.contains("secret-clinic") ?? true)
        XCTAssertFalse(reason?.logDescription.contains("Appointment") ?? true)
        XCTAssertEqual(ExclusionReason.privateBrowsing.logDescription, "private browsing window")
    }

    // MARK: - What the Settings UI reads

    func testTheSnapshotGivesTheUITheLockedRowsAndTheCategories() {
        let engine = makeEngine()
        engine.setExcluded(true, bundleID: "com.acme.app", displayName: "Acme")

        let snapshot = engine.snapshot()

        XCTAssertEqual(
            snapshot.appCategories.map(\.category), [.passwordManagers],
            "the Apps tab shows the app categories only")
        XCTAssertEqual(snapshot.websiteCategories.map(\.category), [.banks])
        XCTAssertEqual(snapshot.appCategories.first?.title, "Password Managers")
        XCTAssertEqual(snapshot.appCategories.first?.subtitle, "Password manager apps")
        XCTAssertEqual(snapshot.websiteCategories.first?.subtitle, "UK & US banks, neobanks, and fintech")

        // Locked rows first, then the user's own — and the user's row is removable.
        XCTAssertTrue(snapshot.excludedApps.prefix(ExclusionCatalog.lockedApps.count).allSatisfy(\.isLocked))
        let acme = snapshot.excludedApps.first { $0.app.bundleID == "com.acme.app" }
        XCTAssertEqual(acme?.state, .excluded)
        XCTAssertFalse(acme?.isLocked ?? true)

        // The System group: Login Screen locked, the rest offered and unticked.
        let login = snapshot.systemSurfaces.first { $0.app.bundleID == "com.apple.loginwindow" }
        XCTAssertEqual(login?.state, .lockedExcluded)
        let notifications = snapshot.systemSurfaces.first {
            $0.app.bundleID == "com.apple.notificationcenterui"
        }
        XCTAssertEqual(notifications?.state, .included)
    }

    func testCategoryWebsiteRowsAreNotIndividuallyRemovable() {
        let engine = makeEngine()
        engine.excludeWebsite("example.com")
        engine.setCategory(.banks, excluded: true)

        let websites = engine.snapshot().websites

        XCTAssertEqual(websites.first { $0.pattern.host == "example.com" }?.isLocked, false)
        XCTAssertEqual(websites.first { $0.pattern.host == "chase.com" }?.fromCategory, .banks)
        XCTAssertEqual(websites.first { $0.pattern.host == "chase.com" }?.isLocked, true)
    }

    func testObserversSeeEveryChangeSoTheUIStaysLive() {
        let engine = makeEngine()
        let seen = Counts()
        let token = engine.addObserver { set in seen.record(set.websites.count) }

        engine.excludeWebsite("example.com")
        engine.excludeWebsite("other.example")
        engine.removeObserver(token)
        engine.excludeWebsite("third.example")

        XCTAssertEqual(seen.values, [0, 1, 2], "the initial state, then one call per change, then silence")
    }

    func testARepeatedChangeIsNotACharge() {
        let engine = makeEngine()

        XCTAssertEqual(engine.setCategory(.banks, excluded: true), .applied)
        let generation = engine.generation
        XCTAssertEqual(engine.setCategory(.banks, excluded: true), .unchanged)
        XCTAssertEqual(engine.generation, generation, "an unchanged state must not invalidate tickets")
        XCTAssertEqual(engine.setExcluded(true, bundleID: "   "), .rejected)
    }

    // MARK: - Cost

    /// The gate runs on every capture tick for the life of the machine, next to a 3 s cadence.
    func testTheGateIsCheapEnoughToRunOnEveryTick() {
        let set = ExclusionSet.make(
            configuration: {
                var configuration = ExclusionConfiguration()
                configuration.excludedCategories = ExclusionCategory.allCases.map(\.rawValue)
                configuration.excludedDomains = (0..<200).map { "site\($0).example.com" }
                configuration.excludedApps = (0..<200).map {
                    ExcludableApp(bundleID: "com.example.app\($0)", displayName: "App \($0)")
                }
                return configuration
            }(),
            health: .configured)
        let subject = CaptureSubject(
            bundleID: "com.apple.Safari", appName: "Safari",
            windowTitle: "Lisbon in November — Wikipedia", url: "https://en.wikipedia.org/wiki/Lisbon")

        let started = Date()
        for _ in 0..<1_000 { _ = CapturePolicy.exclusion(for: subject, using: set) }
        let elapsed = Date().timeIntervalSince(started)

        // Written against a measured regression, not a guess: comparing 250 patterns by normalising
        // both sides per comparison took 3.5 s for this loop. Normalising the candidate once takes
        // single-digit milliseconds, so half a second still catches that class of mistake with room
        // to spare on a loaded CI box.
        XCTAssertLessThan(elapsed, 0.5, "a thousand ticks is an hour of capture: \(elapsed)s")
    }
}
