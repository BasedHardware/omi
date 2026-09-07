import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The user's transparency slider: what it maps to, that it persists, that it announces itself, and
/// that the glass really follows it.
///
/// Held as values for the reason `InkGlass` is: the surface cannot be rendered offscreen, so the
/// claims are arithmetic on the ground plus one AppKit view driven through its real seam.
@MainActor
final class InkGlassTransparencyTests: XCTestCase {

  private func suite() throws -> UserDefaults {
    let name = "InkGlassTransparencyTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
    defaults.removePersistentDomain(forName: name)
    addTeardownBlock { defaults.removePersistentDomain(forName: name) }
    return defaults
  }

  // MARK: - The mapping

  func testTheDefaultIsExactlyTheScrimTheDesignShipped() {
    XCTAssertEqual(
      InkGlass.scrim(forTransparency: InkGlass.defaultTransparency), InkGlass.scrim, accuracy: 0.0001,
      "nothing may look different until somebody moves the slider")
    XCTAssertEqual(
      InkGlass.groundAlpha(reduceTransparency: false, transparency: InkGlass.defaultTransparency),
      InkGlass.groundAlpha(reduceTransparency: false), accuracy: 0.0001)
  }

  func testTheEndsAreAnOpaqueSheetAndTheBareMaterial() {
    XCTAssertEqual(InkGlass.scrim(forTransparency: 0), 1, accuracy: 0.0001, "0 is solid")
    XCTAssertEqual(InkGlass.scrim(forTransparency: 1), 0, accuracy: 0.0001, "1 is the blur alone")
  }

  func testTheMappingIsMonotoneAndClamped() {
    var previous = InkGlass.scrim(forTransparency: 0)
    for step in stride(from: CGFloat(0.05), through: 1, by: 0.05) {
      let scrim = InkGlass.scrim(forTransparency: step)
      XCTAssertLessThan(scrim, previous, "more transparency must mean less scrim at \(step)")
      previous = scrim
    }
    XCTAssertEqual(InkGlass.scrim(forTransparency: -3), 1, accuracy: 0.0001)
    XCTAssertEqual(InkGlass.scrim(forTransparency: 7), 0, accuracy: 0.0001)
  }

  func testReduceTransparencyWinsOverTheSlider() {
    for transparency in [CGFloat(0), 0.3, InkGlass.defaultTransparency, 1] {
      XCTAssertEqual(
        InkGlass.groundAlpha(reduceTransparency: true, transparency: transparency), 1, accuracy: 0.0001,
        "glass that honours the slider but ignores the setting is the defect the setting exists for")
    }
  }

  // MARK: - The settings object

  func testAFreshInstallStartsAtTheDefault() throws {
    let settings = InkGlassTransparencySettings(defaults: try suite(), notificationCenter: NotificationCenter())
    XCTAssertTrue(settings.isDefault)
    XCTAssertEqual(settings.transparency, InkGlass.defaultTransparency, accuracy: 0.0001)
  }

  func testAChangePersistsAndComesBackOnTheNextLaunch() throws {
    let defaults = try suite()
    let first = InkGlassTransparencySettings(defaults: defaults, notificationCenter: NotificationCenter())
    first.transparency = 0.8
    XCTAssertFalse(first.isDefault)

    let second = InkGlassTransparencySettings(defaults: defaults, notificationCenter: NotificationCenter())
    XCTAssertEqual(second.transparency, 0.8, accuracy: 0.0001)

    second.resetToDefault()
    let third = InkGlassTransparencySettings(defaults: defaults, notificationCenter: NotificationCenter())
    XCTAssertTrue(third.isDefault)
  }

  func testAnOutOfRangeWriteOrStoredValueIsClamped() throws {
    let defaults = try suite()
    let settings = InkGlassTransparencySettings(defaults: defaults, notificationCenter: NotificationCenter())
    settings.transparency = 4
    XCTAssertEqual(settings.transparency, 1, accuracy: 0.0001)
    settings.transparency = -1
    XCTAssertEqual(settings.transparency, 0, accuracy: 0.0001)

    defaults.set(-2.0, forKey: InkGlassTransparencySettings.defaultsKey)
    let reloaded = InkGlassTransparencySettings(defaults: defaults, notificationCenter: NotificationCenter())
    XCTAssertEqual(
      reloaded.transparency, 0, accuracy: 0.0001, "a hand-edited preference cannot produce a negative alpha")
  }

  func testEveryChangeIsAnnouncedOnItsOwnCentre() throws {
    let center = NotificationCenter()
    let settings = InkGlassTransparencySettings(defaults: try suite(), notificationCenter: center)
    var seen: [CGFloat] = []
    let token = center.addObserver(
      forName: InkGlassTransparencySettings.didChangeNotification, object: nil, queue: nil
    ) { note in
      let sender = note.object as? InkGlassTransparencySettings
      MainActor.assumeIsolated { seen.append(sender?.transparency ?? -1) }
    }
    defer { center.removeObserver(token) }

    // Three writes, the way a slider delivers them: every intermediate value, not just the release.
    settings.transparency = 0.2
    settings.transparency = 0.25
    settings.transparency = 0.3
    XCTAssertEqual(seen.count, 3, "a panel re-applies on every step, or it does not follow the thumb")
    XCTAssertEqual(seen.last ?? -1, 0.3, accuracy: 0.0001, "the observer re-reads the object, and gets the new value")
  }

  // MARK: - The glass follows it

  /// The AppKit panel, driven through the same seam production uses, really paints the ground at
  /// the alpha the slider asks for — and goes opaque under Reduce Transparency regardless.
  func testTheAppKitPanelPaintsTheGroundAtTheSlidersAlpha() throws {
    let view = InkGlassView(frame: NSRect(x: 0, y: 0, width: 200, height: 100), style: .panel())
    for transparency in [CGFloat(0), 0.25, InkGlass.defaultTransparency, 0.9, 1] {
      view.apply(reduceTransparency: false, transparency: transparency)
      let alpha = try XCTUnwrap(view.ground.layer?.backgroundColor?.alpha)
      XCTAssertEqual(
        alpha, InkGlass.scrim(forTransparency: transparency), accuracy: 0.002,
        "at transparency \(transparency) the ground is not the alpha the slider asked for")
    }

    view.apply(reduceTransparency: true, transparency: 1)
    let opaque = try XCTUnwrap(view.ground.layer?.backgroundColor?.alpha)
    XCTAssertEqual(
      opaque, 1, accuracy: 0.0001, "the slider at its clearest still yields a solid sheet under the setting")
    XCTAssertTrue(view.material.isHidden)
  }

  /// The SwiftUI panel — the one every content page wears — follows the object it observes without
  /// being rebuilt: one modifier value, and the ground it resolves moves with every write to the
  /// settings object it was handed. This is the path a slider in Settings drives while its thumb is
  /// down.
  ///
  /// Read at the modifier's own seam, not sampled from pixels: the panel mounts two representables
  /// (the material and the hit-region reporter) and neither renders offscreen — `ImageRenderer`
  /// paints a representable as an opaque placeholder, and an unhosted `NSVisualEffectView` draws a
  /// solid stand-in — so a bitmap of the panel reads the same white at every transparency.
  func testTheSwiftUIPanelFollowsTheSettingsObjectItObserves() throws {
    let settings = InkGlassTransparencySettings(defaults: try suite(), notificationCenter: NotificationCenter())
    let panel = InkGlassPanelModifier(
      cornerRadius: 0, shadow: nil, reduceTransparency: false, transparency: settings)

    settings.transparency = 0
    let solid = panel.resolvedGroundAlpha
    settings.transparency = 1
    let clear = panel.resolvedGroundAlpha
    settings.transparency = InkGlass.defaultTransparency
    let shipped = panel.resolvedGroundAlpha

    XCTAssertEqual(solid, 1, accuracy: 0.0001, "at 0 the panel is an opaque sheet")
    XCTAssertLessThan(clear, shipped, "at 1 more of the desktop comes through than at the shipped scrim")
    XCTAssertLessThan(shipped, solid, "the shipped scrim is not opaque")
    XCTAssertGreaterThan(solid - clear, 0.25, "the slider has to make a visible difference, not a nominal one")

    // One glass, two hosts: the SwiftUI panel resolves exactly the alpha the AppKit panel paints.
    for transparency in [CGFloat(0), 0.25, InkGlass.defaultTransparency, 0.9, 1] {
      settings.transparency = transparency
      XCTAssertEqual(
        panel.resolvedGroundAlpha, InkGlass.scrim(forTransparency: transparency), accuracy: 0.0001,
        "at transparency \(transparency) the SwiftUI panel and the AppKit panel disagree on the ground")
    }

    // Reduce Transparency, requested on the panel, wins over the object it observes.
    let sheet = InkGlassPanelModifier(
      cornerRadius: 0, shadow: nil, reduceTransparency: true, transparency: settings)
    settings.transparency = 1
    XCTAssertEqual(
      sheet.resolvedGroundAlpha, 1, accuracy: 0.0001, "the slider at its clearest still yields a solid sheet")
  }

  /// The row is in Settings search, so the setting is reachable by name.
  func testTransparencyIsSearchableInSettings() {
    let ids = Set(SettingsSearchItem.allSearchableItems.map(\.settingId))
    XCTAssertTrue(ids.contains("general.transparency"))
  }
}
