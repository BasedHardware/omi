import Foundation

/// The connectors the background refresh scheduler knows about.
///
/// Gmail is deliberately absent: its reader is being replaced by the
/// server-side OAuth work in https://github.com/BasedHardware/omi/pull/10969,
/// and adding an adapter against the cookie-scraping reader would be a
/// same-week rewrite. It joins the registry with the same
/// `supportsUnattendedRefresh` reasoning as Calendar once that lands.
enum ConnectorRefreshRegistry {
  @MainActor
  static func live() -> [any BackgroundRefreshableConnector] {
    [
      CalendarBackgroundRefreshAdapter(),
      AppleNotesBackgroundRefreshAdapter(),
      LocalFilesBackgroundRefreshAdapter(),
    ]
  }
}
