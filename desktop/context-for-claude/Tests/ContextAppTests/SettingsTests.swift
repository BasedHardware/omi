import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// The Settings window's decisions, tested where they are decidable without a screen.
///
/// Nothing here asserts visual fidelity — that is what the screenshots in the PR are for. What is
/// asserted is the set of properties a rendering bug cannot hide: that the destructive storage strategy
/// cannot be reached without a second deliberate action, that the accent palette contains no purple,
/// that a locked exclusion is undrawable as removable, and that "System" appearance means *no override*
/// rather than a snapshot of whatever the system happened to be.
final class SettingsTests: XCTestCase {

    /// A store with its own defaults suite and no reach into `NSApp`, so nothing here can leave a
    /// preference behind or flip the test process's activation policy.
    @MainActor
    private func makeStore() -> SettingsStore {
        let suite = "context.settings.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        return SettingsStore(defaults: defaults, appliesToRunningApp: false)
    }

    // MARK: - Appearance (I14)

    /// The whole point of Phase 0: `System` installs no appearance at all.
    ///
    /// A mapping that resolved `system` to `.aqua` or `.darkAqua` would re-introduce the exact defect
    /// `docs/first-run-experience.md` § 0.1 removed — a process pinned to one appearance while the
    /// system menu around it is the other — and it would then go stale the moment the user changed
    /// their own Appearance setting.
    func testSystemAppearanceMeansNoOverride() {
        XCTAssertNil(AppearanceOverride.system.nsAppearanceName)
        XCTAssertNil(AppearanceOverride.system.nsAppearance)
        XCTAssertEqual(AppearanceOverride.light.nsAppearanceName, .aqua)
        XCTAssertEqual(AppearanceOverride.dark.nsAppearanceName, .darkAqua)
    }

    @MainActor
    func testAppearanceDefaultsToSystemAndPersists() {
        let suite = "context.settings.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }

        let first = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        XCTAssertEqual(first.appearance, .system, "System is the default; Light/Dark are overrides")
        first.appearance = .dark

        let second = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        XCTAssertEqual(second.appearance, .dark)
    }

    // MARK: - Accent (I15, INV-UI-1)

    /// `INV-UI-1`: never purple, anywhere.
    ///
    /// Asserted on the resolved sRGB *pixel* rather than on the case names, because a future
    /// maintainer renaming a case does not change what it paints — and through `BrandColour` rather
    /// than through a band of hue degrees.
    ///
    /// The band this replaces was `hue >= 250 && hue <= 345`. It looked like a guard and was not one:
    /// `systemIndigo` renders at 233.8° and slips under the lower bound, `systemPink` at 348.0° and
    /// slips over the upper one, so the two colours nearest to being wrongly added were exactly the
    /// two it could not see. It passed only because `AccentChoice` happens to ship neither — the same
    /// failure the timeline palette shipped a violet through, with different constants.
    /// `testTheAccentGuardRejectsTheColoursTheOldBandAdmitted` pins that both are now rejected.
    ///
    /// `.system` is excluded from the sweep and that is deliberate: it resolves to
    /// `NSColor.controlAccentColor`, which is the accent the *user* chose in System Settings. If they
    /// picked purple for their own Mac that is their decision, and overriding it would be the same
    /// brand imposition Phase 0 removed. INV-UI-1 governs the colours this app ships, which is
    /// `AccentChoice.named`.
    func testAccentPaletteOffersNoPurple() {
        XCTAssertFalse(AccentChoice.named.isEmpty)
        for choice in AccentChoice.named {
            guard let nsColor = choice.nsColor else {
                XCTFail("\(choice.title) has no colour of its own")
                continue
            }
            // A near-grey has no meaningful hue; Graphite is the one such choice, and `BrandColour`
            // skips it on the same 0.15 saturation threshold this used to apply here by hand.
            assertReadsOnBrand(nsColor, choice.title)
        }
    }

    /// The accent guard's own regression test: the colours the band it replaced let through.
    ///
    /// A brand guard and a blind brand guard are indistinguishable while the list is clean, which is
    /// how the band survived. This is the difference between them.
    func testTheAccentGuardRejectsTheColoursTheOldBandAdmitted() {
        // Both of these satisfied `hue >= 250 && hue <= 345` — indigo below it, pink above it.
        assertReadsOffBrand(.systemIndigo, "systemIndigo (233.8°)")
        assertReadsOffBrand(.systemPink, "systemPink (348.0°)")
        // The one the old band did catch, so the rebase is not a trade.
        assertReadsOffBrand(.systemPurple, "systemPurple (292.7°)")

        // And everything the pane actually offers must stay offerable — including `systemRed`, which
        // renders at 359.0° and is a degree inside the wedge's red edge. That is what
        // `BrandColour.redEdgeTolerance` exists for, and this is the test that would fail if the
        // tolerance were removed or the rule made symmetric.
        let offered: [(String, NSColor)] = [
            ("Azure", .systemBlue), ("Teal", .systemTeal), ("Green", .systemGreen),
            ("Yellow", .systemYellow), ("Orange", .systemOrange), ("Red", .systemRed),
            ("Graphite", .systemGray),
        ]
        for (title, colour) in offered { assertReadsOnBrand(colour, title) }
    }

    /// The default accent must be the user's own, so that picking nothing changes nothing.
    func testSystemAccentIsTheUsersOwn() {
        XCTAssertNil(AccentChoice.system.nsColor, "System must not name a colour of its own")
        XCTAssertFalse(AccentChoice.named.contains(.system))
        for name in AccentChoice.allCases.map(\.title) {
            let lower = name.lowercased()
            XCTAssertFalse(lower.contains("purple"), "\(name) names a forbidden hue")
            XCTAssertFalse(lower.contains("violet"), "\(name) names a forbidden hue")
            XCTAssertFalse(lower.contains("magenta"), "\(name) names a forbidden hue")
            XCTAssertFalse(lower.contains("pink"), "\(name) names a forbidden hue")
        }
    }

    // MARK: - Timeline controls (I17–I22)

    /// The preview reflects the toggles, and hiding a control never removes the chord that drives it.
    func testTimelineVisibilityDrivesThePreviewAndKeepsShortcuts() {
        var controls = TimelineControlVisibility()
        XCTAssertEqual(controls.visible.count, TimelineControlVisibility.Control.allCases.count)

        controls[.zoomControls] = false
        XCTAssertFalse(controls.visible.contains(.zoomControls))
        XCTAssertEqual(controls.visible, [.openExternally, .liveText, .segmentNavigation])

        // The hint is a property of the control, not of its visibility — which is what makes
        // "their keyboard shortcuts keep working even when a control is hidden" true rather than
        // decorative.
        XCTAssertEqual(TimelineControlVisibility.Control.zoomControls.shortcutHint, "⌘ ⇧ + / −")
        XCTAssertEqual(TimelineControlVisibility.Control.segmentNavigation.shortcutHint, "⌥ ← / →")
        XCTAssertEqual(TimelineControlVisibility.Control.openExternally.shortcutHint, "↵")
        // Live Text has no chord in `RewindView`, so it must not advertise one.
        XCTAssertNil(TimelineControlVisibility.Control.liveText.shortcutHint)
    }

    /// The preview's strip has to read as a *sweep* — that is the property these eight hand-picked
    /// names own, and the one the palette cannot supply.
    ///
    /// This test used to also assert that none of the eight fell inside `TimelinePreview.violetBand`
    /// (`215..<250`). That constant and that assertion are gone, retired rather than rebased onto
    /// `BrandColour`, for two reasons. The brand property is now proven at the generator:
    /// `RewindTests` checks the rendered colour of all 2503 values `RewindPalette` can emit, so eight
    /// names drawn from that same generator cannot produce a violet, and restating it here over a
    /// handful of them is coverage theatre — worse, a band whose floor (215°) sits below the arc's
    /// ceiling (220°) is a test that has almost no room left to fail. And the constant was a hazard
    /// in itself: it is exactly the kind of number a future reader uses to re-derive a ceiling, and
    /// it encoded the *old* one.
    func testTimelinePreviewSampleAppsSweepTheArc() {
        XCTAssertFalse(TimelinePreview.sampleApps.isEmpty)
        let hues = TimelinePreview.sampleApps.map(RewindPalette.hue(forApp:))
        XCTAssertGreaterThan(
            (hues.max() ?? 0) - (hues.min() ?? 0), 150,
            "the preview's segments must span the arc, not cluster")
    }

    @MainActor
    func testTimelineVisibilityRoundTripsThroughDefaults() {
        let suite = "context.settings.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }

        let first = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        var controls = first.timelineControls
        controls[.liveText] = false
        first.timelineControls = controls

        let second = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        XCTAssertFalse(second.timelineControls.liveText)
        XCTAssertTrue(second.timelineControls.openExternally)
    }

    // MARK: - Capture (I25)

    func testCaptureQualitySubtitleDescribesTheSelectionAndDefaultMatchesCapture() {
        XCTAssertEqual(CaptureQuality.default, .standard)
        // The `Default` tile must describe what capture actually does today, or the pane is claiming a
        // setting that is not the setting. The two numbers are `ScreenPipeline.maxPixelSize` (1600) and
        // `ScreenPipeline.frameQuality` (0.20) in `Sources/ContextApp/Capture/ScreenWatcher.swift`,
        // pinned as literals here because that type is `private` to that file and cannot be imported.
        // If capture retunes either, this fails and the tile's copy has to follow it.
        XCTAssertEqual(CaptureQuality.standard.longestSide, 1600)
        XCTAssertEqual(CaptureQuality.standard.compressionQuality, 0.20, accuracy: 0.0001)

        // Monotonic in both knobs, so the four tiles are one scale rather than four opinions.
        let ordered: [CaptureQuality] = [.best, .standard, .compact, .smallest]
        for (finer, coarser) in zip(ordered, ordered.dropFirst()) {
            XCTAssertGreaterThan(finer.longestSide, coarser.longestSide)
            XCTAssertGreaterThan(finer.compressionQuality, coarser.compressionQuality)
        }

        for quality in CaptureQuality.allCases {
            XCTAssertTrue(
                quality.subtitle.contains("\(quality.longestSide) px"),
                "\(quality.title)'s subtitle must state the resolution it actually stores")
        }
    }

    // MARK: - Storage (I27–I30)

    func testStorageDefaultsToOffAndCommitsImmediately() {
        var selection = StorageSelection()
        XCTAssertEqual(selection.strategy, .off, "Off is the default")
        XCTAssertFalse(selection.isAwaitingConfirmation)
        XCTAssertEqual(selection.select(.off), .unchanged)
    }

    /// `I30`: Limit deletes user data permanently, so one click on the radio button must not be enough.
    func testLimitRequiresAnExplicitConfirmation() {
        var selection = StorageSelection()

        XCTAssertEqual(selection.select(.limit), .awaitingConfirmation)
        // Parked, not in force. Anything reading `strategy` still sees Off, which is what stops a
        // deletion sweep starting behind an unanswered sheet.
        XCTAssertEqual(selection.strategy, .off)
        XCTAssertEqual(selection.highlighted, .limit, "the radio shows what is being asked about")
        XCTAssertTrue(selection.isAwaitingConfirmation)

        XCTAssertEqual(selection.confirm(), .committed)
        XCTAssertEqual(selection.strategy, .limit)
        XCTAssertFalse(selection.isAwaitingConfirmation)
    }

    func testCancellingADestructiveStrategyLeavesTheOldOneInForce() {
        var selection = StorageSelection()
        selection.select(.limit)
        selection.cancel()
        XCTAssertEqual(selection.strategy, .off)
        XCTAssertEqual(selection.highlighted, .off)
        XCTAssertFalse(selection.isAwaitingConfirmation)
    }

    /// Compress re-encodes lossily, so it is destructive too and gets the same gate.
    func testEveryDataDestroyingStrategyIsGated() {
        for strategy in StorageStrategy.allCases where strategy.destroysExistingData {
            var selection = StorageSelection()
            XCTAssertEqual(
                selection.select(strategy), .awaitingConfirmation,
                "\(strategy.title) destroys data and must not commit on one click")
        }
        XCTAssertFalse(StorageStrategy.off.destroysExistingData)
    }

    @MainActor
    func testStoreNeverPersistsAnUnconfirmedStrategy() {
        let store = makeStore()
        XCTAssertEqual(store.selectStorage(.limit), .awaitingConfirmation)
        XCTAssertEqual(store.storage.strategy, .off)
        XCTAssertEqual(store.storageLimitSummary, "no storage limits set")

        store.confirmStorage()
        XCTAssertEqual(store.storage.strategy, .limit)
        XCTAssertTrue(store.storageLimitSummary.hasPrefix("limited to "))
    }

    /// Every threshold the stepper can reach must print as a round number.
    ///
    /// The bug this pins: the default was `5 * 1024³` and `ByteCountFormatter(.file)` counts decimal
    /// gigabytes, so the confirmation asked "Delete recordings once **5.37 GB** is reached?" while the
    /// stepper moved in whole units. Verified against the live dialog before the units were changed.
    func testEveryReachableThresholdPrintsAsARoundNumber() {
        XCTAssertEqual(StorageLimit.format(StorageLimit.defaultBytes), "5 GB")
        XCTAssertEqual(StorageLimit.format(StorageLimit.minimumBytes), "1 GB")
        XCTAssertEqual(StorageLimit.format(StorageLimit.maximumBytes), "200 GB")
        var bytes = StorageLimit.minimumBytes
        while bytes <= StorageLimit.maximumBytes {
            XCTAssertFalse(
                StorageLimit.format(bytes).contains("."),
                "\(bytes) prints as \(StorageLimit.format(bytes)), which is not a round number")
            bytes += StorageLimit.stepBytes
        }
    }

    @MainActor
    func testStorageThresholdIsClampedToTheOfferedRange() {
        let store = makeStore()
        store.storageLimitBytes = 1
        XCTAssertEqual(store.storageLimitBytes, StorageLimit.minimumBytes)
        store.storageLimitBytes = Int64.max / 2
        XCTAssertEqual(store.storageLimitBytes, StorageLimit.maximumBytes)
    }

    /// `I27`: the header figure is measured from a real directory, not estimated.
    func testStorageIsMeasuredFromTheRealDirectory() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("context-storage-\(UUID().uuidString)", isDirectory: true)
        let day = root.appendingPathComponent("Frames/2026-07-29", isDirectory: true)
        try FileManager.default.createDirectory(at: day, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        try Data(repeating: 0xab, count: 4_096).write(to: day.appendingPathComponent("frame_a.heic"))
        try Data(repeating: 0xcd, count: 8_192).write(to: day.appendingPathComponent("frame_b.heic"))
        try Data(repeating: 0x01, count: 1_024).write(to: root.appendingPathComponent("notes.txt"))

        let usage = StorageMeasurement.measure(directory: root)
        XCTAssertEqual(usage.fileCount, 3)
        XCTAssertFalse(usage.isPartial)
        // Allocated size rounds up to block boundaries, so this is a floor rather than an equality.
        XCTAssertGreaterThanOrEqual(usage.totalBytes, 13_312)
        XCTAssertGreaterThan(usage.totalBytes, 0)
        XCTAssertFalse(usage.formattedTotal.isEmpty)
    }

    // MARK: - Exclusions (I31–I40)

    /// Rows come out of the engine's snapshot in the reference's order, and the locked ones are
    /// undrawable as removable.
    func testAppSectionsFollowTheReferenceOrderAndLockRowsAreNotRemovable() {
        let engine = makeEngine()
        let model = ExclusionsPaneModel.make(tab: .apps, snapshot: engine.snapshot())

        XCTAssertEqual(
            model.sections.map(\.id), ["categories", "excluded", "system"],
            "Categories, then Excluded, then System — with the two discovery lists absent when empty")
        XCTAssertEqual(
            model.sections.map(\.title), ["Categories", "Excluded", "System"])

        let excluded = try? XCTUnwrap(model.sections.first { $0.id == "excluded" })
        let lockedRows = (excluded?.rows ?? []).filter { !$0.isRemovable }
        XCTAssertFalse(lockedRows.isEmpty, "the locked defaults must be present")
        for row in lockedRows {
            XCTAssertTrue(row.isChecked, "a locked default renders excluded")
            XCTAssertFalse(row.isRemovable, "and the user cannot clear it")
        }

        // Keychain Access is the reference's own example of the locked state.
        let keychain = excluded?.rows.first { $0.id == "app:com.apple.keychainaccess" }
        XCTAssertNotNil(keychain)
        XCTAssertEqual(keychain?.isRemovable, false)
    }

    /// The engine refuses the mutation too, so the greyed checkbox is not the only thing standing
    /// between a click and a plaintext copy of a vault.
    func testTheEngineRefusesToUnlockALockedRow() {
        let engine = makeEngine()
        XCTAssertEqual(
            engine.setExcluded(false, bundleID: "com.apple.keychainaccess"), .refusedLocked)
        let model = ExclusionsPaneModel.make(tab: .apps, snapshot: engine.snapshot())
        let row = model.sections.flatMap(\.rows).first { $0.id == "app:com.apple.keychainaccess" }
        XCTAssertEqual(row?.isChecked, true)
    }

    /// A locked row for an app the user does not have is noise, and fourteen of them buried the three
    /// sections below. Hiding them must not weaken what the section *claims*, so the footnote counts them.
    func testLockedRowsForUninstalledAppsAreHiddenButStillClaimed() {
        let engine = makeEngine()
        let installedOnly = [
            ExcludableApp(bundleID: "com.apple.keychainaccess", displayName: "Keychain Access"),
            ExcludableApp(bundleID: "com.apple.Passwords", displayName: "Passwords"),
            ExcludableApp(bundleID: "com.apple.finder", displayName: "Finder"),
        ]
        let model = ExclusionsPaneModel.make(
            tab: .apps, snapshot: engine.snapshot(), allApps: installedOnly)

        let excluded = model.sections.first { $0.id == "excluded" }
        XCTAssertEqual(
            excluded?.rows.map(\.id),
            ["app:com.apple.keychainaccess", "app:com.apple.Passwords"],
            "only the password managers actually on this Mac are listed")
        XCTAssertEqual(
            excluded?.footnote,
            "Password managers are excluded by default and cannot be removed. "
                + "12 more are covered but are not installed on this Mac.")

        // And the engine still refuses every one of them, listed or not — hiding a row is not lifting it.
        XCTAssertEqual(engine.setExcluded(false, bundleID: "com.bitwarden.desktop"), .refusedLocked)
        XCTAssertEqual(engine.state(ofBundleID: "com.bitwarden.desktop"), .lockedExcluded)
    }

    /// Before the inventory has been read there is no way to know what is installed, so nothing is
    /// filtered — the list must never be briefly empty.
    func testLockedRowsAreAllShownUntilTheInventoryIsKnown() {
        let engine = makeEngine()
        let model = ExclusionsPaneModel.make(tab: .apps, snapshot: engine.snapshot())
        let excluded = model.sections.first { $0.id == "excluded" }
        XCTAssertEqual(excluded?.rows.count, ExclusionCatalog.passwordManagers.count)
        XCTAssertEqual(
            excluded?.footnote,
            "Password managers are excluded by default and cannot be removed.")
    }

    func testRecentAndAllApplicationSectionsAppearAndDoNotDuplicateAnApp() {
        let engine = makeEngine()
        // `Passwords` is already a locked row, so it must not appear a second time under a discovery
        // heading — two checkboxes for one app is two chances to disagree about its state.
        let recent = [
            ExcludableApp(bundleID: "com.apple.Passwords", displayName: "Passwords"),
            ExcludableApp(bundleID: "company.thebrowser.Browser", displayName: "Arc"),
        ]
        let all = [
            ExcludableApp(bundleID: "company.thebrowser.Browser", displayName: "Arc"),
            ExcludableApp(bundleID: "com.apple.finder", displayName: "Finder"),
        ]

        let model = ExclusionsPaneModel.make(
            tab: .apps, snapshot: engine.snapshot(), recentApps: recent, allApps: all)

        XCTAssertEqual(
            model.sections.map(\.title),
            ["Categories", "Excluded", "System", "Recently Recorded", "All Applications"])

        let ids = model.sections.flatMap(\.rows).map(\.id)
        XCTAssertEqual(ids.count, Set(ids).count, "no app may be drawn twice")
        // Passwords is a locked default. It is not in `allApps` here, so it is hidden from Excluded —
        // and it must still not resurface under Recently Recorded as a clearable checkbox.
        XCTAssertFalse(
            ids.contains("app:com.apple.Passwords"),
            "a locked app hidden from Excluded must not reappear as an ordinary row")
        XCTAssertEqual(
            model.sections.first { $0.id == "recent" }?.rows.map(\.id), ["app:company.thebrowser.Browser"])
        XCTAssertEqual(
            model.sections.first { $0.id == "all" }?.rows.map(\.id), ["app:com.apple.finder"])
    }

    /// The bug this pins: the canonical browser set is spelled lower case, and the database stores
    /// identifiers as the vendor ships them (`company.thebrowser.Browser`, `com.google.Chrome`). A raw
    /// `Set.contains` matched none of them, so Recently Recorded came back empty on a machine with a
    /// month of browsing in it. Verified against the real database, which holds `company.thebrowser.Browser`
    /// with a capital B.
    func testBrowserIdentifierMatchingIsCaseFolded() {
        let folded = ExclusionInventory.browserBundleIdentifiers
        for identifier in ["company.thebrowser.Browser", "com.google.Chrome", "com.apple.Safari"] {
            XCTAssertTrue(
                folded.contains(identifier.lowercased()),
                "\(identifier) must match after folding")
        }
        XCTAssertTrue(
            folded.allSatisfy { $0 == $0.lowercased() },
            "the set itself has to be folded, or the comparison is folded on one side only")
        // The canonical set lives in ContextCore; this only widens it for discovery.
        XCTAssertTrue(folded.isSuperset(of: PrivateBrowsing.browserBundleIdentifiers.map { $0.lowercased() }))
    }

    /// An empty Recently Recorded list must say why rather than looking like a broken feature.
    func testEmptyRecentDomainsExplainsItself() {
        let engine = makeEngine()
        let model = ExclusionsPaneModel.make(tab: .websites, snapshot: engine.snapshot())
        let recent = model.sections.first { $0.id == "recent" }
        XCTAssertEqual(recent?.rows.count, 0)
        XCTAssertEqual(recent?.footnote, ExclusionsPaneModel.noRecentDomainsNote)

        let populated = ExclusionsPaneModel.make(
            tab: .websites, snapshot: engine.snapshot(), recentDomains: ["anthropic.com"])
        let filled = populated.sections.first { $0.id == "recent" }
        XCTAssertEqual(filled?.rows.map(\.id), ["recent:anthropic.com"])
        XCTAssertNil(filled?.footnote)
    }

    func testWebsiteTabOrderAndCategoryContributedDomainsAreLocked() {
        let engine = makeEngine()
        engine.setCategory(.banks, excluded: true)
        engine.excludeWebsite("example.com")

        let model = ExclusionsPaneModel.make(tab: .websites, snapshot: engine.snapshot())
        XCTAssertEqual(
            model.sections.map(\.title),
            ["Categories", "Private Browsing", "Excluded", "Recently Recorded"])

        let rows = model.sections.first { $0.id == "excluded" }?.rows ?? []
        let own = rows.first { $0.id == "site:example.com" }
        XCTAssertEqual(own?.isRemovable, true, "the user's own domain is removable")

        let fromCategory = rows.first { $0.id == "site:chase.com" }
        XCTAssertNotNil(fromCategory, "a ticked category contributes its domains")
        XCTAssertEqual(fromCategory?.isRemovable, false, "and they are not individually removable")
    }

    /// `I39`: the copy must not overclaim. Safari genuinely cannot be detected, and the markers are
    /// English-only, so the row has to say both.
    func testPrivateTabsCopyDoesNotOverclaim() {
        let copy = ExclusionsPaneModel.privateTabsSubtitle
        XCTAssertTrue(
            copy.contains("Safari"), "the one browser this cannot cover has to be named")
        XCTAssertTrue(copy.localizedCaseInsensitiveContains("cannot be detected"))
        XCTAssertTrue(copy.localizedCaseInsensitiveContains("English"))
        XCTAssertFalse(
            copy.localizedCaseInsensitiveContains("all supported browsers"),
            "the reference's blanket claim is false for us")
    }

    /// The Private Browsing switch is a setting, not a list entry, so a search for a domain must not
    /// make it disappear.
    func testSearchFiltersRowsButKeepsThePrivateTabsSwitch() {
        let engine = makeEngine()
        engine.excludeWebsite("monzo.com")
        let model = ExclusionsPaneModel.make(
            tab: .websites, snapshot: engine.snapshot(), query: "monzo")

        XCTAssertTrue(model.sections.contains { $0.id == "privateTabs" })
        let hosts = model.sections.flatMap(\.rows).compactMap { row -> String? in
            if case .website(let pattern, _) = row { return pattern.host }
            return nil
        }
        XCTAssertEqual(hosts, ["monzo.com"])
    }

    func testTypingAHostOffersItAsAnAdditionAndAnAlreadyExcludedOneDoesNot() {
        let engine = makeEngine()
        let offered = ExclusionsPaneModel.make(
            tab: .websites, snapshot: engine.snapshot(), query: "https://Example.COM/login?x=1")
        XCTAssertEqual(offered.addableDomain?.host, "example.com")

        engine.excludeWebsite("example.com")
        let already = ExclusionsPaneModel.make(
            tab: .websites, snapshot: engine.snapshot(), query: "example.com")
        XCTAssertNil(already.addableDomain, "already excluded, so there is nothing to add")

        let prose = ExclusionsPaneModel.make(
            tab: .websites, snapshot: engine.snapshot(), query: "my bank")
        XCTAssertNil(prose.addableDomain, "prose is not a host")
    }

    /// `I40`: a favicon is a network request, so Airgap Mode has to suppress the *request*. The pane
    /// asks the engine rather than deciding for itself, which is what makes hiding-an-already-fetched
    /// image impossible as a shortcut.
    func testAirgapModeSuppressesFaviconFetches() {
        let engine = makeEngine()
        guard case .allowed(let url) = engine.faviconFetch(for: "anthropic.com") else {
            return XCTFail("a favicon should be fetchable with Airgap off")
        }
        // The domain's own favicon, never a third party's — a service would learn every domain the
        // user chose to hide.
        XCTAssertEqual(url.host(), "anthropic.com")

        engine.setAirgapMode(true)
        XCTAssertEqual(engine.faviconFetch(for: "anthropic.com"), .suppressed(.airgapMode))
        XCTAssertFalse(engine.isFaviconFetchAllowed)
    }

    // MARK: - Agents (I9, I13)

    /// The Claude-target dropdown's one home.
    ///
    /// `context.settings.claudeTarget` is written here and nowhere else, and `ClaudeHandoff` is the
    /// only thing that reads it — see `ClaudeHandoffTests.testTheHandoffRoutesToTheTargetChosenInSettings`
    /// for the other half, which is that choosing Terminal actually sends the question there. The two
    /// halves matter together: this store persisted the choice perfectly for a whole release while
    /// the handoff ignored it, which is a setting that lies rather than a setting that works.
    @MainActor
    func testTheClaudeTargetDefaultsToTheAppAndPersists() {
        let suite = "context.settings.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }

        let first = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        XCTAssertEqual(
            first.claudeTarget, .claudeApp,
            "the app is the default: it is the target that needs nothing installed beyond Claude itself")
        first.claudeTarget = .terminal

        let second = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        XCTAssertEqual(second.claudeTarget, .terminal)
    }

    /// Detection reads the disk. The seam is injected so this asserts the *mapping*, not what happens
    /// to be installed on the machine running the suite.
    func testAgentDetectionReportsWhatIsActuallyThere() {
        let claudeApp = URL(fileURLWithPath: "/Applications/Claude.app")
        let detector = AgentDetector(
            applicationForBundleID: { $0 == "com.anthropic.claudefordesktop" ? claudeApp : nil },
            isExecutableFile: { $0.hasSuffix("/codex") && $0.contains("/opt/homebrew/") },
            isDirectory: { _ in false })

        XCTAssertEqual(detector.presence(of: .claude), .application(claudeApp))
        XCTAssertEqual(detector.presence(of: .codex), .executable("/opt/homebrew/bin/codex"))
        // The seam is always handed an absolute path, so no implementation of it has to expand `~`.
        XCTAssertEqual(detector.presence(of: .codex).detail, "/opt/homebrew/bin/codex")
        XCTAssertEqual(detector.presence(of: .cursor), .absent)

        XCTAssertEqual(detector.presence(of: .claude).label, "Installed")
        XCTAssertEqual(detector.presence(of: .codex).label, "Installed")
        // The requirement is explicit that a not-installed state has to exist.
        XCTAssertEqual(detector.presence(of: .cursor).label, "Not installed")
        XCTAssertFalse(detector.presence(of: .cursor).isInstalled)
    }

    /// A state directory is real evidence but weaker than a binary, and must not read as `Installed`.
    func testAConfiguredButUninstalledAgentIsNotReportedAsInstalled() {
        let detector = AgentDetector(
            applicationForBundleID: { _ in nil },
            isExecutableFile: { _ in false },
            isDirectory: { $0.contains(".codex") })

        XCTAssertEqual(detector.presence(of: .codex), .configured(AgentDetector.expand("~/.codex")))
        XCTAssertEqual(detector.presence(of: .codex).detail, "~/.codex")
        XCTAssertEqual(detector.presence(of: .codex).label, "Configured")
        XCTAssertTrue(detector.presence(of: .codex).isInstalled)
    }

    /// No absolute path with the user's name in it may reach the window or a log line.
    func testAgentDetailPathsAreHomeRelative() {
        let detector = AgentDetector(
            applicationForBundleID: { _ in nil },
            isExecutableFile: { $0 == AgentDetector.expand("~/.claude/local/claude") },
            isDirectory: { _ in false })
        let detail = detector.presence(of: .claude).detail
        XCTAssertEqual(detail, "~/.claude/local/claude")
        XCTAssertFalse(
            detail?.hasPrefix("/Users") ?? true,
            "an absolute home path carries the user's name into the window and any log line")
    }

    // MARK: - Shortcuts (I1–I3)

    /// The two defaults the reference names, printed the way it prints them.
    func testDefaultChordsPrintAsTheReferenceWritesThem() {
        XCTAssertEqual(ShortcutAction.openTimeline.defaultChord.displayString, "⌘⌘")
        XCTAssertEqual(ShortcutAction.openSearch.defaultChord.displayString, "⌘⌘⇧")
        XCTAssertEqual(
            ShortcutAction.openTimeline.subtitle,
            "Record a keyboard shortcut. Clear it to use ⌘⌘.")
        XCTAssertEqual(
            ShortcutAction.openSearch.subtitle,
            "Record a keyboard shortcut. Clear it to use ⌘⌘⇧.")
    }

    @MainActor
    func testRecordingClearingAndRefusal() {
        let provider = InMemoryShortcutBindings()
        XCTAssertEqual(provider.binding(for: .openTimeline), ShortcutAction.openTimeline.defaultChord)

        let chord = SettingsShortcutChord(keyCode: 40, modifierFlags: [.command, .shift])
        XCTAssertEqual(provider.record(chord, for: .openTimeline), .recorded)
        XCTAssertEqual(provider.binding(for: .openTimeline), chord)

        // Cleared is a real state, not an error: the slot falls back to the default chord, which is
        // exactly what "Clear it to use ⌘⌘" describes.
        provider.clear(.openTimeline)
        XCTAssertNil(provider.binding(for: .openTimeline))

        // A recorder that always succeeded would let the user bind ⌘Q.
        let quit = SettingsShortcutChord(keyCode: 12, modifierFlags: .command)
        guard case .rejected = provider.record(quit, for: .openTimeline) else {
            return XCTFail("⌘Q is reserved by macOS and must be refused")
        }

        // And the two slots may not collide with each other.
        provider.record(chord, for: .openTimeline)
        guard case .rejected = provider.record(chord, for: .openSearch) else {
            return XCTFail("one chord cannot drive two actions")
        }
    }

    /// `I3`: the conflict row is a live query, so an empty answer means no row at all.
    @MainActor
    func testConflictsAreQueriedAndResolvable() {
        XCTAssertTrue(InMemoryShortcutBindings().conflicts().isEmpty)

        let conflict = SettingsShortcutConflict(
            action: .openTimeline,
            owner: "Codex",
            chord: ShortcutAction.openTimeline.defaultChord,
            remedyTitle: "Switch Codex to ⌥⌥")
        let provider = InMemoryShortcutBindings(conflicts: [conflict])

        XCTAssertEqual(provider.conflicts(), [conflict])
        XCTAssertEqual(conflict.title, "Codex also uses ⌘⌘")
        XCTAssertEqual(conflict.subtitle, "Context for Claude and Codex both use ⌘⌘.")

        provider.resolve(conflict)
        XCTAssertTrue(provider.conflicts().isEmpty, "the one-click switch clears the row")
    }

    @MainActor
    func testObserversAreNotifiedAndReleased() {
        let provider = InMemoryShortcutBindings()
        var notifications = 0
        let token = provider.addObserver { notifications += 1 }
        provider.clear(.openSearch)
        XCTAssertEqual(notifications, 1)

        provider.removeObserver(token)
        provider.clear(.openTimeline)
        XCTAssertEqual(notifications, 1)
    }

    // MARK: - The window's own contract

    /// The sidebar is six panes in the documented order, each with a symbol that resolves.
    func testSixPanesInOrderWithResolvableSymbols() {
        XCTAssertEqual(
            SettingsPane.allCases.map(\.title),
            ["General", "Agents", "Appearance", "Capture", "Storage", "Exclusions"])
        for pane in SettingsPane.allCases {
            XCTAssertNotNil(
                NSImage(systemSymbolName: pane.symbol, accessibilityDescription: nil),
                "\(pane.title)'s symbol \(pane.symbol) does not exist on this system")
        }
    }

    /// `I6`/`I7`: the version comes from the bundle, and there is no updater to advertise.
    func testVersionIsReadFromTheBundle() {
        XCTAssertTrue(AppVersion.display.hasPrefix("Version "))
        XCTAssertTrue(AppVersion.display.contains(AppVersion.short))
        XCTAssertTrue(AppVersion.display.contains(AppVersion.build))
    }

    // MARK: - Helpers

    /// A fresh engine on a temporary configuration file, so the pane's derivation is asserted against
    /// real engine state rather than a hand-built snapshot that could disagree with it.
    private func makeEngine() -> ExclusionEngine {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("context-exclusions-\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        return ExclusionEngine(
            configurationURL: root.appendingPathComponent("exclusions.json"),
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
    }
}
