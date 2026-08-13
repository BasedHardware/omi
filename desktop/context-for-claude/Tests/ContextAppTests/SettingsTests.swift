import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// The Settings window's decisions, tested where they are decidable without a screen.
///
/// Nothing here asserts visual fidelity — that is what the screenshots in the PR are for. What is
/// asserted is the set of properties a rendering bug cannot hide: that the destructive storage strategy
/// cannot be reached without a second deliberate action *and cannot be lost to one either*, that every
/// string describing that strategy discloses both of the bounds it enforces, that a locked exclusion is
/// undrawable as removable, and that "System" appearance means *no override* rather than a snapshot of
/// whatever the system happened to be.
///
/// The accent-palette tests that used to sit here are gone with the palette: the Appearance pane's
/// accent dropdown reached nothing but `.tint()` on its own window and its default resolved to the
/// machine's `controlAccentColor`, which is purple on a Mac set to purple. `INV-UI-1` is now carried
/// entirely by `Ink.accent`, whose guard is `InkAccentTests` over the shared `BrandColourGuard`
/// predicate — including that predicate's own regression test for `systemIndigo` and `systemPink`.
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

    // MARK: - The brand-colour guard (INV-UI-1)

    /// `BrandColour`'s own regression test: the colours the hue band it replaced let through.
    ///
    /// **Kept although the accent palette it was written beside is gone.** The band was
    /// `hue >= 250 && hue <= 345`, and it was blind in both directions: `systemIndigo` renders at
    /// 233.8° and slips under the lower bound, `systemPink` at 348.0° and slips over the upper one.
    /// A brand guard and a blind brand guard are indistinguishable while nothing tries either colour,
    /// which is how the band survived a whole release — so this is the only test in the suite that
    /// tells them apart, and deleting it with the palette would leave `BrandColour` unguarded against
    /// exactly the two failures it was built for. It never referenced the palette: every value below
    /// is a system colour.
    func testTheBrandGuardRejectsTheColoursTheOldHueBandAdmitted() {
        // Both of these satisfied `hue >= 250 && hue <= 345` — indigo below it, pink above it.
        assertReadsOffBrand(.systemIndigo, "systemIndigo (233.8°)")
        assertReadsOffBrand(.systemPink, "systemPink (348.0°)")
        // The one the old band did catch, so the rebase is not a trade.
        assertReadsOffBrand(.systemPurple, "systemPurple (292.7°)")

        // And the far side: the warm colours the product does draw have to stay passable, including
        // `systemRed`, which renders at 359.0° and is a degree inside the wedge's red edge. That is
        // what `BrandColour.redEdgeTolerance` exists for, and this is the assertion that would fail
        // if the tolerance were removed or the rule made symmetric.
        let onBrand: [(String, NSColor)] = [
            ("systemBlue", .systemBlue), ("systemTeal", .systemTeal), ("systemGreen", .systemGreen),
            ("systemYellow", .systemYellow), ("systemOrange", .systemOrange), ("systemRed", .systemRed),
            ("systemGray", .systemGray),
        ]
        for (title, colour) in onBrand { assertReadsOnBrand(colour, title) }
    }

    // No test here re-asserts that Settings does not read the machine's accent: deleting
    // `AccentChoice` moves `Sources/ContextApp` to the end state `InkAccentTests` already sweeps for.
    // Its `testNoUISourceReadsTheMachinesAccent` flags any file reading `controlAccentColor` outside
    // `declaredAccentIntake`, and that allowlist's own documentation names an empty list as the goal.
    // A second checker here would be the duplicate that guard was written to make unnecessary.

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

    /// The tiles are one scale, and each one's copy states its own number.
    ///
    /// **This deliberately no longer pins `standard.longestSide == 1600`.** That assertion was
    /// written when capture hard-coded `ScreenPipeline.maxPixelSize` and `frameQuality`, and it
    /// guarded the tile's copy against drifting from those constants. Both are gone: capture now
    /// reads `quality.longestSide` and `quality.compressionQuality` from this same enum, so the
    /// assertion had become the enum compared with itself — a literal restated in two files, which
    /// fails only when someone edits both and passes whenever the product is wrong. The behavioural
    /// guard that replaced it is `CapturePacingTests`, which encodes a synthetic screen through
    /// `FrameImage` at every tile and asserts the stored pixels and the stored byte ordering. What is
    /// left here is what this file is for: properties of the *copy*.
    func testCaptureQualityTilesAreOneScaleAndEachStatesItsOwnResolution() {
        XCTAssertEqual(CaptureQuality.default, .standard)

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

    /// The tile that costs history has to say so.
    ///
    /// `Best Quality` is ~2.25× the pixels of `Default` at nearly twice the encoder quality, and the
    /// retention sweep deletes oldest-first the moment the frames folder passes the user's threshold
    /// (`Engine.scheduleRetentionSweep` → `enforceRetention(olderThanDays:toFitBytes:)`). So picking
    /// this tile shortens how much history a given Storage limit holds — a consequence "largest
    /// files" does not convey, and the same omission the Storage strings were fixed for.
    ///
    /// A copy assertion, and it is a static tripwire rather than behavioural coverage: it proves the
    /// sentence exists, not that the sweep obeys it. The sweep's own bounds are asserted in
    /// `testEveryStringDescribingLimitDisclosesTheAgePrune` and in `ContextCoreTests`.
    func testBestQualityDisclosesThatItShortensHistoryUnderAStorageLimit() {
        let best = CaptureQuality.best.subtitle
        XCTAssertTrue(
            best.localizedCaseInsensitiveContains("limit"),
            "Best Quality must name the setting its cost lands on: \(best)")
        XCTAssertTrue(
            best.localizedCaseInsensitiveContains("fewer days"),
            "…and say what is lost, not only that files are larger: \(best)")
    }

    /// Pause on Inactivity must not change an existing user's capture on their behalf.
    ///
    /// `ScreenWatcher.tick` is the first reader this preference has ever had, so no install has a
    /// stored value and every one of them lands on this default. Defaulting it on would stop screen
    /// capture five minutes after the last keystroke for every user who never opened this pane —
    /// and invisibly, because the idle branch only logs and never reaches `Engine.pausedReason`, so
    /// the menu bar goes on reading *Listening*. This asserts the default that keeps their capture
    /// exactly as it is today.
    @MainActor
    func testPauseOnInactivityIsOffUntilTheUserAsksForIt() {
        XCTAssertFalse(
            makeStore().pausesOnInactivity,
            "a preference with no prior reader must not switch capture off for existing users")

        // …and it is a real preference, not a constant: turning it on survives a relaunch.
        let suite = "context.settings.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        SettingsStore(defaults: defaults, appliesToRunningApp: false).pausesOnInactivity = true
        XCTAssertTrue(SettingsStore(defaults: defaults, appliesToRunningApp: false).pausesOnInactivity)
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

    /// Every strategy that destroys data is gated, and there is at least one — a vacuous sweep passes.
    ///
    /// The group used to have a third option, `Compress`, whose red destructive confirmation warned
    /// that "the original detail cannot be recovered" and which then did nothing at all: the retention
    /// sweep tests `strategy == .limit` and no re-encoder exists in this package. It is deleted rather
    /// than implemented, because a destructive-role warning in front of a no-op trains the user to
    /// dismiss the next one, and the next one really does delete.
    func testEveryDataDestroyingStrategyIsGated() {
        let destructive = StorageStrategy.allCases.filter(\.destroysExistingData)
        XCTAssertEqual(destructive, [.limit], "Limit is the one strategy that touches what is on disk")
        for strategy in destructive {
            var selection = StorageSelection()
            XCTAssertEqual(
                selection.select(strategy), .awaitingConfirmation,
                "\(strategy.title) destroys data and must not commit on one click")
        }
        XCTAssertFalse(StorageStrategy.off.destroysExistingData)
    }

    /// A persisted `"compress"` from a build that offered it must not survive as anything.
    ///
    /// Both readers decode the raw value — `SettingsStore.init` here and `EngineStore`'s sweep — and
    /// both fall back to `off` on a value they do not know, so the retired case degrades to "delete
    /// nothing". That is why the deletion needed no migration, and this is the assertion that says so.
    @MainActor
    func testARetiredStrategyOnDiskFallsBackToOff() {
        let suite = "context.settings.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        defaults.set("compress", forKey: "context.settings.storageStrategy")

        XCTAssertNil(StorageStrategy(rawValue: "compress"))
        let store = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        XCTAssertEqual(store.storage.strategy, .off)
    }

    /// **The age prune is disclosed wherever Limit is described.**
    ///
    /// `Limit` is two bounds, not one: `ContextStore.enforceRetention` prunes by age *and* by bytes,
    /// and `Engine.ensureStorage` starts the sweep with 30 days. For a whole release no string the
    /// user could read mentioned age at all, so setting a 200 GB threshold with 8 GB on disk read as
    /// "nothing will be deleted" while everything older than a month was deleted anyway — permanent,
    /// undisclosed loss of their data. Every surface that describes the strategy has to say it, which
    /// is why all four are asserted here rather than only the confirmation.
    @MainActor
    func testEveryStringDescribingLimitDisclosesTheAgePrune() {
        let store = makeStore()
        let pane = SettingsStoragePane(store: store)
        let days = "\(StorageLimit.retentionDays) days"

        // While the choice is parked, the pane is drawing the confirmation about it.
        store.selectStorage(.limit)
        XCTAssertTrue(pane.confirmationPresentation.wrappedValue)
        // Captured while pending, because both are empty once the choice is committed.
        let confirmationBody = pane.confirmationMessage
        var surfaces: [(String, String)] = [
            ("the radio row", StorageStrategy.limit.subtitle),
            ("the confirmation title", pane.confirmationTitle),
            ("the confirmation body", confirmationBody),
        ]

        // And once it is in force the header caption is the line the user reads without opening
        // anything, so it has to carry the same disclosure.
        store.confirmStorage()
        surfaces.append(("the header caption", store.storageLimitSummary))

        for (surface, copy) in surfaces {
            XCTAssertTrue(
                copy.contains(days),
                "\(surface) does not disclose that recordings older than \(days) are deleted: \(copy)")
        }

        // The body also has to say the threshold does not hold them, or a user reads two rules and
        // assumes the larger one wins.
        XCTAssertTrue(
            confirmationBody.localizedCaseInsensitiveContains("whatever the threshold"),
            "the confirmation must say a bigger threshold does not keep older recordings")
        // Off promises the opposite and must keep promising it.
        XCTAssertEqual(StorageStrategy.off.subtitle, "Keep all your data. Forever.")
    }

    /// `I30`'s other half: the confirmed choice must survive whichever order SwiftUI uses.
    ///
    /// The bug this pins: the dialog's `isPresented` setter called `cancelStorageChange()` on every
    /// dismissal. SwiftUI is free to write that binding *before* it runs the tapped button's action,
    /// and when it did, `cancel()` had already nulled the `pending` that `confirmStorage()` promotes —
    /// so the user's deliberate second click returned `.unchanged` and silently did nothing. Both
    /// orderings are driven here through the pane's real binding, because a binding built inside
    /// `body` is unreachable from a test, which is why this was invisible to one.
    @MainActor
    func testConfirmingSurvivesEitherOrderOfBindingWriteAndButtonAction() {
        // Ordering A: SwiftUI writes `isPresented = false` first, then runs the action.
        let first = makeStore()
        let firstPane = SettingsStoragePane(store: first)
        first.selectStorage(.limit)
        XCTAssertTrue(firstPane.confirmationPresentation.wrappedValue)
        firstPane.confirmationPresentation.wrappedValue = false
        first.confirmStorage()
        XCTAssertEqual(first.storage.strategy, .limit, "the dismissal must not eat the pending choice")
        XCTAssertFalse(firstPane.confirmationPresentation.wrappedValue)

        // Ordering B: the action runs first, then the dismissal is written.
        let second = makeStore()
        let secondPane = SettingsStoragePane(store: second)
        second.selectStorage(.limit)
        second.confirmStorage()
        secondPane.confirmationPresentation.wrappedValue = false
        XCTAssertEqual(second.storage.strategy, .limit)
        XCTAssertFalse(secondPane.confirmationPresentation.wrappedValue)
    }

    /// Cancelling is still one deliberate click, and it still puts the old strategy back.
    @MainActor
    func testTheCancelButtonIsWhatCancels() {
        let store = makeStore()
        let pane = SettingsStoragePane(store: store)
        store.selectStorage(.limit)
        XCTAssertEqual(store.storage.highlighted, .limit)

        store.cancelStorageChange()
        XCTAssertEqual(store.storage.strategy, .off)
        XCTAssertEqual(store.storage.highlighted, .off)
        XCTAssertFalse(pane.confirmationPresentation.wrappedValue, "the dialog closes with the pending")
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

    /// `I39`: the copy must not overclaim. Some browsers genuinely cannot be detected, and the
    /// markers are English-only, so the row has to say both.
    func testPrivateTabsCopyDoesNotOverclaim() {
        let copy = ExclusionsPaneModel.privateTabsSubtitle
        for browser in ExclusionsPaneModel.privateBrowsingUndetectableBrowsers {
            XCTAssertTrue(copy.contains(browser), "a browser this cannot cover has to be named")
        }
        XCTAssertTrue(copy.localizedCaseInsensitiveContains("cannot be detected"))
        XCTAssertTrue(copy.localizedCaseInsensitiveContains("English"))
        XCTAssertFalse(
            copy.localizedCaseInsensitiveContains("all supported browsers"),
            "the reference's blanket claim is false for us")
    }

    /// The bug this pins: **Arc was advertised as covered and never was.**
    ///
    /// The row said it skips "Chrome, Edge, Brave, Arc and Firefox" private windows, recognised from
    /// the window title. Arc's window title is the bare page title — measured across 925 Arc frames in
    /// the real database on this machine, every one of the 13 distinct titles is a page name
    /// (`Anthropic`, `LinkedIn`, `(9) Home / X`) with no browser chrome in it at all, so not one of
    /// `PrivateBrowsing.titleMarkers` can ever match. `OpenExternally` documents the same titles from
    /// the other direction. A privacy control that names a browser it cannot see is worse than one
    /// that admits the gap, because the user stops checking.
    ///
    /// The two lists are what the sentence is built from, so a future edit cannot move a browser
    /// between them in prose only.
    func testPrivateTabsNamesArcAsUndetectableRatherThanCovered() {
        let detectable = ExclusionsPaneModel.privateBrowsingDetectableBrowsers
        let undetectable = ExclusionsPaneModel.privateBrowsingUndetectableBrowsers
        XCTAssertFalse(detectable.contains("Arc"), "no title marker can match an Arc window title")
        XCTAssertFalse(detectable.contains("Safari"))
        XCTAssertEqual(undetectable, ["Arc", "Safari"])
        XCTAssertTrue(Set(detectable).isDisjoint(with: undetectable))

        // The claim survives only while the markers really are English title substrings — if
        // `PrivateBrowsing` ever gains a real per-browser signal, the lists have to be revisited
        // rather than left as prose.
        XCTAssertEqual(
            PrivateBrowsing.classify(bundleID: "company.thebrowser.Browser", title: "Anthropic"),
            .unknown,
            "a real Arc title carries no evidence either way, which is why Arc cannot be listed")
        XCTAssertEqual(
            PrivateBrowsing.classify(bundleID: "com.google.Chrome", title: "Anthropic - Incognito"),
            .privateBrowsing,
            "and Chrome is listed because its title does carry the marker")
    }

    /// The pane has to say what an exclusion does *not* stop.
    ///
    /// `ScreenWatcher` is the only caller of `ExclusionEngine.admit`/`revalidate`; no audio source
    /// consults the engine at all. So excluding an app suppresses its screenshots, OCR, window title
    /// and accessibility text, and leaves microphone and system-audio transcription running — which
    /// nothing on this pane used to mention. On a privacy pane that omission is the failure.
    func testExclusionsScopeNoteSaysScreenOnlyAndNamesWhatStopsAudio() {
        let note = ExclusionsPaneModel.scopeNote
        XCTAssertTrue(note.localizedCaseInsensitiveContains("screen capture"))
        XCTAssertTrue(
            note.localizedCaseInsensitiveContains("audio is not covered"),
            "the pane must state plainly that audio is outside exclusions: \(note)")
        XCTAssertTrue(
            note.localizedCaseInsensitiveContains("pause"),
            "and name the control that does stop audio, or the caveat is not actionable")
    }

    /// …and it must not claim an excluded *site* is never read, because recognising one requires
    /// reading it.
    ///
    /// The two verdicts are taken at different points and the difference is the user's to know. An
    /// app is refused by the `exclusionReason` call `ScreenWatcher` makes from the bundle identifier
    /// alone, before it resolves a window — nothing about it is read. A site has no identity until
    /// something is read: the window title is scrubbed and the accessibility tree walked for a page
    /// address before `admit` is asked, and in `websiteReason`'s third tier — no address readable at
    /// all — the screenshot is taken and OCR'd first, with `revalidate` refusing at the write barrier
    /// and `discard` unlinking the image already on disk. Nothing excluded is *stored* either way,
    /// and that is the promise the note is now allowed to make.
    ///
    /// A copy assertion, so a static tripwire: the behaviour it describes is covered by
    /// `ContextCoreTests/ExclusionsTests`, not here.
    func testExclusionsScopeNoteDoesNotClaimAnExcludedSiteIsNeverRead() {
        let note = ExclusionsPaneModel.scopeNote
        XCTAssertFalse(
            note.localizedCaseInsensitiveContains("never read"),
            "an excluded site's title, address and text are read in order to recognise it: \(note)")
        XCTAssertTrue(
            note.localizedCaseInsensitiveContains("app is refused before"),
            "the note must still make the stronger promise for apps, where it is true: \(note)")
        XCTAssertTrue(
            note.localizedCaseInsensitiveContains("recognised"),
            "and say why a site is read at all: \(note)")
        XCTAssertTrue(
            note.localizedCaseInsensitiveContains("deleted instead of stored"),
            "and that what was read is discarded rather than kept: \(note)")
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

    /// The Airgap row must not claim more than `NetworkEgress` enforces.
    ///
    /// It opened with "Stops all network access", and that was false in a way the user could not
    /// discover: the switch is enforced against this app's seven `NetworkEgress.Client` cases and
    /// against `OmiBackend` inside the MCP server, and against nothing else. The MCP server's local
    /// tools are ungated on purpose — `ContextMCPKit/Airgap.swift` states the reason — so with the
    /// switch on, asking Claude what you were working on returns OCR'd screen text and Claude carries
    /// it to Anthropic. That is the product working; the sentence claiming otherwise was the defect.
    ///
    /// A copy assertion, so a static tripwire. The enforcement it describes is behavioural elsewhere:
    /// `AirgapEgressTests` for this app's clients, `ContextMCPKitTests/AirgapTests` for the server's.
    func testTheAirgapSubtitleClaimsOnlyWhatIsEnforced() {
        let subtitle = SettingsGeneralPane.airgapSubtitle
        XCTAssertFalse(
            subtitle.localizedCaseInsensitiveContains("all network access"),
            "the MCP tools still read local capture on request, so this is not all network access")
        XCTAssertTrue(
            subtitle.localizedCaseInsensitiveContains("this app"),
            "the subject of the promise is this app, and the sentence has to say so: \(subtitle)")
        XCTAssertTrue(
            subtitle.localizedCaseInsensitiveContains("mcp"),
            "and it has to name what is still reachable: \(subtitle)")
        XCTAssertTrue(
            subtitle.localizedCaseInsensitiveContains("anthropic"),
            "and where that goes, which is the part a user cannot infer: \(subtitle)")

        // The clauses that *are* enforced stay named, or the row understates instead. Each maps to a
        // `NetworkEgress.Client` case: conversationUpload/screenActivitySync, listenSocket, the
        // engine's favicon gate, and signIn.
        for promise in ["uploads", "cloud transcription", "favicon", "signing in", "queued"] {
            XCTAssertTrue(
                subtitle.localizedCaseInsensitiveContains(promise),
                "the subtitle dropped an enforced clause: \(promise)")
        }
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
        XCTAssertEqual(ShortcutAction.openActivity.defaultChord.displayString, "⌘ + ⌘")
        XCTAssertEqual(ShortcutAction.openSearch.defaultChord.displayString, "⌘⌘⇧")
        XCTAssertEqual(
            ShortcutAction.openActivity.subtitle,
            "Record a keyboard shortcut. Clear it to use ⌘ + ⌘.")
        XCTAssertEqual(
            ShortcutAction.openSearch.subtitle,
            "Record a keyboard shortcut. Clear it to use ⌘⌘⇧.")
    }

    @MainActor
    func testRecordingClearingAndRefusal() {
        let provider = InMemoryShortcutBindings()
        XCTAssertEqual(provider.binding(for: .openActivity), ShortcutAction.openActivity.defaultChord)

        let chord = SettingsShortcutChord(keyCode: 40, modifierFlags: [.command, .shift])
        XCTAssertEqual(provider.record(chord, for: .openActivity), .recorded)
        XCTAssertEqual(provider.binding(for: .openActivity), chord)

        // Cleared is a real state, not an error: the slot falls back to the default chord, which is
        // exactly what "Clear it to use ⌘ + ⌘" describes.
        provider.clear(.openActivity)
        XCTAssertNil(provider.binding(for: .openActivity))

        // A recorder that always succeeded would let the user bind ⌘Q.
        let quit = SettingsShortcutChord(keyCode: 12, modifierFlags: .command)
        guard case .rejected = provider.record(quit, for: .openActivity) else {
            return XCTFail("⌘Q is reserved by macOS and must be refused")
        }

        // And the two slots may not collide with each other.
        provider.record(chord, for: .openActivity)
        guard case .rejected = provider.record(chord, for: .openSearch) else {
            return XCTFail("one chord cannot drive two actions")
        }
    }

    /// `I3`: the conflict row is a live query, so an empty answer means no row at all.
    @MainActor
    func testConflictsAreQueriedAndResolvable() {
        XCTAssertTrue(InMemoryShortcutBindings().conflicts().isEmpty)

        let conflict = SettingsShortcutConflict(
            action: .openActivity,
            owner: "Codex",
            chord: ShortcutAction.openActivity.defaultChord,
            remedyTitle: "Switch Codex to ⌥⌥")
        let provider = InMemoryShortcutBindings(conflicts: [conflict])

        XCTAssertEqual(provider.conflicts(), [conflict])
        XCTAssertEqual(conflict.title, "Codex also uses ⌘ + ⌘")
        XCTAssertEqual(conflict.subtitle, "Context for Claude and Codex both use ⌘ + ⌘.")

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
        provider.clear(.openActivity)
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
