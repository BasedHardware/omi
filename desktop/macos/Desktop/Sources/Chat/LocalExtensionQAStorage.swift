import Foundation

/// Opt-in isolation for a named QA bundle. Its mock installs must never edit
/// the real user's ~/.omi or hand user extensions to the fixture runtime.
enum LocalExtensionQAStorage {
  static func root(
    enabled: Bool,
    isNonProduction: Bool,
    bundleIdentifier: String,
    temporaryDirectory: URL
  ) -> URL? {
    guard enabled, isNonProduction, bundleIdentifier.hasPrefix("com.omi.omi-"),
      bundleIdentifier.utf8.count <= 200,
      bundleIdentifier.utf8.allSatisfy({
        (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0)
          || $0 == 45 || $0 == 46 || $0 == 95
      })
    else { return nil }
    return temporaryDirectory.appendingPathComponent(
      "omi-extension-qa-\(bundleIdentifier)", isDirectory: true)
  }
}
