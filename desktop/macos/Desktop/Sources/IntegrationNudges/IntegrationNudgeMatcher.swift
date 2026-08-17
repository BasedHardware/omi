import Foundation

/// Resolves "which integration is this window about?" from the frontmost app.
///
/// Pure and synchronous so the whole recognition surface — including every
/// false-positive risk in the browser-title heuristics — is unit-testable
/// without a window server.
enum IntegrationNudgeMatcher {
  struct Match: Equatable {
    let entry: IntegrationNudgeCatalogEntry
    let trigger: IntegrationNudgeTrigger
  }

  /// The frontmost window, as much of it as the app can see.
  ///
  /// `windowTitle` is nil when Screen Recording permission has not been granted.
  /// That degrades browser-site recognition to nothing and leaves native-app
  /// recognition working, which is the right failure direction: a missed nudge,
  /// never a wrong one.
  struct Window: Equatable {
    let bundleIdentifier: String?
    let windowTitle: String?

    init(bundleIdentifier: String?, windowTitle: String? = nil) {
      self.bundleIdentifier = bundleIdentifier
      self.windowTitle = windowTitle
    }
  }

  /// Returns the first catalog entry the window matches, or nil.
  ///
  /// Native-app triggers are evaluated before browser-title triggers across the
  /// whole catalog. A bundle identifier is an exact fact; a window title is a
  /// guess, so the fact wins. Without this ordering, ChatGPT.app — whose window
  /// title also contains "ChatGPT" — could be attributed to the browser trigger
  /// and reported under the wrong `trigger_kind`.
  static func match(_ window: Window, in catalog: [IntegrationNudgeCatalogEntry] = IntegrationNudgeCatalog.nudgeable)
    -> Match?
  {
    if let bundleIdentifier = window.bundleIdentifier {
      for entry in catalog {
        for trigger in entry.triggers {
          guard case .application(let identifiers) = trigger.match else { continue }
          if identifiers.contains(bundleIdentifier) {
            return Match(entry: entry, trigger: trigger)
          }
        }
      }
    }

    guard isBrowser(bundleIdentifier: window.bundleIdentifier),
      let title = window.windowTitle,
      !title.isEmpty
    else { return nil }

    let haystack = normalizedTitle(title)
    for entry in catalog {
      for trigger in entry.triggers {
        guard case .browserTitleSuffix(let suffixes) = trigger.match else { continue }
        if suffixes.contains(where: { haystack.hasSuffix($0.lowercased()) }) {
          return Match(entry: entry, trigger: trigger)
        }
      }
    }

    return nil
  }

  /// Lowercased, trimmed, and stripped of the browser's own trailing chrome so
  /// a site name that a browser appended its product name after still reads as
  /// the end of the title.
  static func normalizedTitle(_ title: String) -> String {
    var value = title.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
    for chrome in [" - google chrome", " — google chrome", " - brave", " - microsoft edge"] {
      if value.hasSuffix(chrome) {
        value = String(value.dropLast(chrome.count)).trimmingCharacters(in: .whitespaces)
      }
    }
    return value
  }

  static func isBrowser(bundleIdentifier: String?) -> Bool {
    guard let bundleIdentifier else { return false }
    return IntegrationNudgeCatalog.browserBundleIdentifiers.contains(bundleIdentifier)
  }
}
