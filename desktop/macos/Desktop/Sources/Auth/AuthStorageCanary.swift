import AppKit
import Foundation

/// Distribution-only, synthetic Keychain proof executed by the signed artifact
/// before Codemagic publishes it. It never handles a real user credential.
enum AuthStorageCanary {
  private static let argumentPrefix = "--auth-storage-canary-result="
  private static let account = "signed-artifact-auth-storage-canary"

  struct Hooks {
    var set: (_ value: String, _ service: String, _ account: String) -> Bool
    var read: (_ service: String, _ account: String) -> String?
    var delete: (_ service: String, _ account: String) -> Void

    nonisolated(unsafe) static let live = Hooks(
      set: { value, service, account in
        DesktopKeychainStore.setString(value, service: service, account: account)
      },
      read: { service, account in
        DesktopKeychainStore.string(service: service, account: account)
      },
      delete: { service, account in
        DesktopKeychainStore.delete(service: service, account: account)
      }
    )
  }

  struct Result: Codable, Equatable {
    let success: Bool
    let stage: String
  }

  static var requestedResultPath: String? {
    CommandLine.arguments.first(where: { $0.hasPrefix(argumentPrefix) })
      .map { String($0.dropFirst(argumentPrefix.count)) }
      .flatMap { $0.isEmpty ? nil : $0 }
  }

  static var isRequested: Bool { requestedResultPath != nil }

  static func execute(hooks: Hooks = .live) -> Result {
    let service = DesktopKeychainStore.scopedService(DesktopKeychainStore.legacyAuthTokenService)
    let sentinel = "omi-auth-canary-\(UUID().uuidString)"

    hooks.delete(service, account)
    guard hooks.set(sentinel, service, account) else {
      return Result(success: false, stage: "write")
    }
    guard hooks.read(service, account) == sentinel else {
      hooks.delete(service, account)
      return Result(success: false, stage: "read_back")
    }
    hooks.delete(service, account)
    guard hooks.read(service, account) == nil else {
      return Result(success: false, stage: "delete")
    }
    return Result(success: true, stage: "complete")
  }

  /// Returns true when canary mode consumed this launch.
  static func runIfRequested() -> Bool {
    guard let resultPath = requestedResultPath else { return false }
    let result = execute()
    do {
      let data = try JSONEncoder().encode(result)
      try data.write(to: URL(fileURLWithPath: resultPath), options: .atomic)
    } catch {
      NSLog("OMI AUTH CANARY: failed to write result: %@", error.localizedDescription)
    }
    NSLog("OMI AUTH CANARY: stage=%@ success=%@", result.stage, result.success ? "true" : "false")
    DispatchQueue.main.async {
      NSApplication.shared.terminate(nil)
    }
    return true
  }
}
