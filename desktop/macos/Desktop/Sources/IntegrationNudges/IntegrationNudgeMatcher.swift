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

    let haystack = title.lowercased()
    for entry in catalog {
      for trigger in entry.triggers {
        guard case .browserTitle(let keywords) = trigger.match else { continue }
        if keywords.contains(where: { containsWholeToken($0.lowercased(), in: haystack) }) {
          return Match(entry: entry, trigger: trigger)
        }
      }
    }

    return nil
  }

  /// Whether `needle` appears in `haystack` as a whole token rather than as a
  /// fragment of a longer word.
  ///
  /// A plain `contains` is wrong here in a way that produces the feature's worst
  /// failure: `"x.com"` matches `max.com`, and every short keyword has a
  /// neighbourhood of unrelated sites it would claim. A token boundary is any
  /// character that is not a letter or digit, so `"x.com"` still matches
  /// `"Home / X.com"` and `"(3) x.com"` but no longer matches `"max.com"`.
  /// Boundaries are computed on the keyword's own ends, so a keyword that
  /// already starts with punctuation (`"/ X"`) is unaffected.
  static func containsWholeToken(_ needle: String, in haystack: String) -> Bool {
    guard !needle.isEmpty else { return false }

    var searchRange = haystack.startIndex..<haystack.endIndex
    while let found = haystack.range(of: needle, range: searchRange) {
      let precededByToken =
        found.lowerBound > haystack.startIndex
        && isTokenCharacter(haystack[haystack.index(before: found.lowerBound)])
      let followedByToken =
        found.upperBound < haystack.endIndex && isTokenCharacter(haystack[found.upperBound])

      // Only guard the ends that are themselves token characters; a keyword
      // beginning or ending in punctuation carries its own boundary.
      let leadingOK = !precededByToken || !isTokenCharacter(needle[needle.startIndex])
      let trailingOK =
        !followedByToken || !isTokenCharacter(needle[needle.index(before: needle.endIndex)])
      if leadingOK && trailingOK { return true }

      guard found.upperBound < haystack.endIndex else { break }
      searchRange = haystack.index(after: found.lowerBound)..<haystack.endIndex
    }
    return false
  }

  private static func isTokenCharacter(_ character: Character) -> Bool {
    character.isLetter || character.isNumber
  }

  static func isBrowser(bundleIdentifier: String?) -> Bool {
    guard let bundleIdentifier else { return false }
    return IntegrationNudgeCatalog.browserBundleIdentifiers.contains(bundleIdentifier)
  }
}
