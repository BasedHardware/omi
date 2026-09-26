//
//  InkGlassTransparency.swift — the user's own say over how much desktop the glass lets through.
//
//  `InkGlass.scrim` is the ground the design ships with, tuned against a measured interference bound
//  (see that constant). It is the right default and it is still only a default: someone on a plain
//  wallpaper wants more of it through, someone who reads over a browser all day wants less, and the
//  system's Reduce Transparency switch is a blunt instrument that also kills the blur. This file is
//  the one knob between those, and it moves the same quantity `scrim` sets — the ground's alpha — so
//  there is still exactly one owner of "what is under the type".
//
//  It is **live**: the value is published, every AppKit `InkGlassView` re-applies on the change
//  notification, and every SwiftUI `inkGlassPanel` observes the object — so the glass follows the
//  slider while the thumb is still moving, not when it is released.
//

import AppKit
import SwiftUI

extension InkGlass {
  /// The user-facing transparency the shipped scrim corresponds to: `1 − scrim`, so the slider's
  /// default sits where the design was tuned and nothing looks different until somebody moves it.
  package static var defaultTransparency: CGFloat { 1 - scrim }

  /// The ground's alpha for a user transparency in `0...1`.
  ///
  /// 0 is an opaque sheet — the same surface Reduce Transparency produces. 1 is the material's own
  /// ceiling: no scrim at all, the blur alone. Between them the scrim is linear in the slider, which
  /// is the only mapping a user can predict. Normalised, so a stale or hand-edited preference cannot
  /// produce a negative alpha, one above opaque, or a NaN the compositor would paint as garbage.
  package static func scrim(forTransparency transparency: CGFloat) -> CGFloat {
    1 - normalizedTransparency(transparency)
  }

  /// The one rule for what a transparency may be: a number in `0...1`. Anything outside the range
  /// is pulled to the nearer end; anything that is not a number at all — `Double("nan")` parses,
  /// and a preference file can hold anything — falls back to the shipped default rather than to an
  /// end, because a value that says nothing should change nothing.
  package static func normalizedTransparency(_ transparency: CGFloat) -> CGFloat {
    guard transparency.isFinite else { return defaultTransparency }
    return min(max(transparency, 0), 1)
  }

  /// The alpha of the `Ink.surface` ground, given both the accessibility setting and the user's
  /// transparency. Reduce Transparency wins outright: glass that honours the slider but ignores the
  /// setting is the defect the setting exists for.
  package static func groundAlpha(reduceTransparency: Bool, transparency: CGFloat) -> CGFloat {
    reduceTransparency ? 1 : scrim(forTransparency: transparency)
  }
}

/// The user's transparency, published, persisted, and announced.
///
/// Mirrors `FontScaleSettings`: one shared object, a `@Published` value SwiftUI binds a slider to,
/// `UserDefaults` behind it. Unlike the font scale, the glass is drawn by AppKit views that are not
/// in any SwiftUI tree, so a change is also posted as a notification for `InkGlassView` to re-apply.
@MainActor
package final class InkGlassTransparencySettings: ObservableObject {
  package static let shared = InkGlassTransparencySettings()

  /// Posted on `notificationCenter` after `transparency` changes. The new value is on the object, not
  /// in `userInfo` — an observer re-reads the one source of truth rather than trusting a payload.
  package static let didChangeNotification = Notification.Name("InkGlassTransparencyDidChange")

  /// The `UserDefaults` key. Stated once, so the seed script and a test can name the same thing.
  package static let defaultsKey = "glassTransparency"

  /// The slider's range: an opaque sheet to the bare material.
  package static let range: ClosedRange<CGFloat> = 0...1

  /// How see-through the glass is, `0...1`. Writes are normalised, persisted and announced.
  ///
  /// A write outside the range (or not a number) is corrected in place. On a `@Published` property
  /// the assignment re-enters this observer with the corrected value, and that inner pass is the one
  /// that persists and announces it — once — so mounted panels follow the correction, not the write.
  /// The correction always lands on a value that needs no further correction, so the re-entry ends
  /// there; a NaN, which is never equal to itself, would otherwise recurse without end.
  @Published package var transparency: CGFloat {
    didSet {
      let normalized = InkGlass.normalizedTransparency(transparency)
      if normalized != transparency {
        transparency = normalized
        return
      }
      defaults.set(Double(transparency), forKey: Self.defaultsKey)
      notificationCenter.post(name: Self.didChangeNotification, object: self)
    }
  }

  package let notificationCenter: NotificationCenter
  private let defaults: UserDefaults

  /// Injectable so a test can run a whole change → persist → announce cycle against its own suite
  /// and its own centre, without touching the user's preferences.
  package init(
    defaults: UserDefaults = .standard,
    notificationCenter: NotificationCenter = .default
  ) {
    self.defaults = defaults
    self.notificationCenter = notificationCenter
    let stored = defaults.object(forKey: Self.defaultsKey) as? Double
    let initial = stored.map { CGFloat($0) } ?? InkGlass.defaultTransparency
    self.transparency = InkGlass.normalizedTransparency(initial)
  }

  package var isDefault: Bool {
    abs(transparency - InkGlass.defaultTransparency) < 0.0001
  }

  package func resetToDefault() {
    transparency = InkGlass.defaultTransparency
  }
}
