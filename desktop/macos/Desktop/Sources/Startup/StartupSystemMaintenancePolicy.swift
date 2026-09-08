import Foundation

struct StartupSystemMaintenanceCommand: Equatable, Sendable {
  let label: String
  let executable: String
  let arguments: [String]
}

/// System commands allowed during normal app startup.
///
/// Keep this list bundle-local. Launching Omi must not mutate shared macOS
/// services such as the Dock or icon cache agents.
enum StartupSystemMaintenancePolicy {
  static func commands(bundlePath: String) -> [StartupSystemMaintenanceCommand] {
    [
      StartupSystemMaintenanceCommand(
        label: "AppDelegate: strip provenance xattrs",
        executable: "/usr/bin/xattr",
        arguments: ["-cr", bundlePath]
      )
    ]
  }
}
