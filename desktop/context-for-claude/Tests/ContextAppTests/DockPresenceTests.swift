import AppKit
import XCTest

@testable import ContextApp

/// **Whether this app shows up in the Dock, decided without an `NSApplication` to decide it on.**
///
/// The app has two homes now — the status item and the Dock — because a 16 pt template mark on a
/// crowded menu bar is genuinely hard to find, and one home that cannot be found is none. Which of
/// them the process actually gets is settled in three places that have no compiler relationship with
/// each other: `Resources/Info.plist` chooses the shape it *launches* in, `ContextAppDelegate`
/// applies the stored preference before anything can draw, and `SettingsStore` applies it again when
/// the row is switched. Every case here exists because drift between two of those three is silent —
/// the app quietly stops having a Dock icon, or quietly stops being able to hide it, and nothing on
/// screen says which.
final class DockPresenceTests: XCTestCase {

    /// The mapping itself.
    ///
    /// `.regular` is the shape with a Dock icon, a ⌘-Tab entry and a menu bar of its own;
    /// `.accessory` is the shape this app shipped as. `.prohibited` is deliberately not a third
    /// case — it is not "even more hidden", it is an app that may not come to the foreground at all,
    /// which would take the status item's popover and every window this app owns with it.
    func testShowingTheIconIsARegularAppAndHidingItIsAnAccessoryApp() {
        XCTAssertEqual(DockPresence.activationPolicy(showsDockIcon: true), .regular)
        XCTAssertEqual(DockPresence.activationPolicy(showsDockIcon: false), .accessory)
    }

    /// **An install that has never opened Settings gets the icon.**
    ///
    /// This is the whole of the reported fix. The row's default is what every existing install falls
    /// through to, and the previous default — off — is what left the menu bar as the only way to
    /// find the app. It is asserted through `showsDockIcon(in:)` rather than by reading the constant,
    /// because the reachable way to get this wrong is `bool(forKey:)`: it answers `false` for a key
    /// nobody has written, so it cannot tell "turned off" from "never opened Settings" and would hand
    /// exactly those users the opposite of the default.
    func testAnInstallThatHasNeverTouchedTheRowGetsADockIcon() {
        let defaults = makeDefaults()

        XCTAssertTrue(DockPresence.showsByDefault)
        XCTAssertTrue(DockPresence.showsDockIcon(in: defaults))
        XCTAssertEqual(DockPresence.launchPolicy(reading: defaults), .regular)
    }

    /// …and a user who turned it off is still off after the relaunch.
    ///
    /// That half is not decoration: the launch path used to install `.accessory` unconditionally as
    /// "belt and braces", which reads the same for a user who wants no Dock icon and swallows the
    /// preference of every user who does.
    func testTheStoredPreferenceSurvivesIntoTheNextLaunchInBothDirections() {
        let defaults = makeDefaults()

        defaults.set(false, forKey: DockPresence.defaultsKey)
        XCTAssertEqual(DockPresence.launchPolicy(reading: defaults), .accessory)

        defaults.set(true, forKey: DockPresence.defaultsKey)
        XCTAssertEqual(DockPresence.launchPolicy(reading: defaults), .regular)
    }

    /// **The row and the launch path have to be reading the same thing.**
    ///
    /// `SettingsStore` writes the preference and `ContextAppDelegate` reads it a process later, with
    /// nothing but a shared string between them. A suite that exercised only one side would pass
    /// happily with the store writing `context.settings.showsDockIcon` and the launch path reading
    /// whatever a rename left behind — and the symptom would be a switch that works until you quit.
    @MainActor
    func testTheSettingsRowAndTheLaunchPathAgreeOnEveryValue() {
        let defaults = makeDefaults()
        let store = SettingsStore(defaults: defaults, appliesToRunningApp: false)

        XCTAssertTrue(store.showsDockIcon, "the row disagrees with DockPresence about the default")

        store.showsDockIcon = false
        XCTAssertFalse(
            DockPresence.showsDockIcon(in: defaults),
            "the launch path cannot see what the row wrote")
        XCTAssertEqual(DockPresence.launchPolicy(reading: defaults), .accessory)

        store.showsDockIcon = true
        XCTAssertEqual(DockPresence.launchPolicy(reading: defaults), .regular)
    }

    /// **A static tripwire over the shipped plist, and not behavioural coverage.**
    ///
    /// It reads `Resources/Info.plist` off disk rather than running anything, and it is here because
    /// the one fact this change turns on is the one a test process cannot observe: which shape macOS
    /// launched it in. `LSUIElement` back at `true` would put the default Dock icon behind a runtime
    /// promotion from `.accessory` to `.regular` — the transition that leaves a promoted app holding
    /// a Dock icon and no menu bar until it has been deactivated and reactivated — and every other
    /// assertion in this file would go on passing.
    ///
    /// The plist is found relative to this source file, the way `InkTestFonts` finds the bundled
    /// faces: the test bundle is not the app bundle, so `Bundle.main` is no use here.
    func testTheShippedInfoPlistDoesNotLaunchTheAppAsAnAccessory() throws {
        let plist = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Resources/Info.plist")

        let parsed = try PropertyListSerialization.propertyList(
            from: try Data(contentsOf: plist), format: nil)
        let info = try XCTUnwrap(parsed as? [String: Any])

        // Absent and `false` mean the same thing to LaunchServices; both are "launch me regular".
        XCTAssertFalse(
            info["LSUIElement"] as? Bool ?? false,
            "LSUIElement is back on, so the Dock icon now depends on a promotion at runtime")
    }

    /// Its own suite per case, so nothing here can leave a preference behind for the next one — or
    /// read one the app itself wrote on this machine.
    private func makeDefaults() -> UserDefaults {
        let suite = "context.dock.tests.\(UUID().uuidString)"
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        return UserDefaults(suiteName: suite)!
    }
}
