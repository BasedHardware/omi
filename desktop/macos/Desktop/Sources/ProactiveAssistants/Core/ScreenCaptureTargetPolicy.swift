/// System-owned foreground targets that ScreenCaptureKit must not treat as
/// ordinary user windows. They are transient during login, lock, and sleep
/// transitions, so capture should stay armed and wait for the next app.
enum ScreenCaptureTargetPolicy {
  private static let unavailableAppNames: Set<String> = [
    "loginwindow",
    "ScreenSaverEngine",
  ]

  static func shouldWaitForUserWindow(appName: String?) -> Bool {
    guard let appName else { return false }
    return unavailableAppNames.contains(appName)
  }
}
