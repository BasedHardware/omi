import Foundation

/// Shared context detection utilities for determining when the user switches contexts
/// (app changes, browser tab switches, etc.)
enum ContextDetection {
  /// Normalize a window title by stripping cosmetic noise (spinners, timers, terminal dimensions)
  /// so that rapid updates from apps like Claude Code or Toggl don't trigger re-analysis.
  static func normalizeWindowTitle(_ title: String?, appName: String? = nil) -> String? {
    ContextTitleNormalizer.normalize(title, appName: appName)
  }

  /// Determine if the user switched contexts by comparing app name and normalized window title.
  /// Returns true if either the app changed or the normalized window title changed.
  static func didContextChange(
    fromApp: String?,
    fromWindowTitle: String?,
    toApp: String?,
    toWindowTitle: String?
  ) -> Bool {
    // App changed
    if fromApp != toApp {
      return true
    }

    // Window title changed (after normalization)
    let normalizedFrom = normalizeWindowTitle(fromWindowTitle, appName: fromApp)
    let normalizedTo = normalizeWindowTitle(toWindowTitle, appName: toApp)
    if normalizedFrom != normalizedTo {
      return true
    }

    return false
  }
}
