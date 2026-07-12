import Foundation

/// A single-use authorization derived from the user's current chat turn.
///
/// The model never supplies this authorization. The primary chat surface creates
/// it from the user's text, then the tool executor consumes it for one matching
/// macOS permission request.
final class PermissionRequestAuthorization {
  enum Permission: String, CaseIterable, Hashable {
    case screenRecording = "screen_recording"
    case microphone
    case notifications
    case accessibility
    case automation
    case fullDiskAccess = "full_disk_access"

    fileprivate var aliases: [String] {
      switch self {
      case .screenRecording:
        return ["screen recording", "screen capture", "screen and system audio recording"]
      case .microphone:
        return ["microphone", "mic"]
      case .notifications:
        return ["notifications", "notification"]
      case .accessibility:
        return ["accessibility"]
      case .automation:
        return ["automation", "apple events"]
      case .fullDiskAccess:
        return ["full disk access", "disk access"]
      }
    }
  }

  private static let authorizationLifetime: TimeInterval = 120
  private var remainingPermissions: Set<Permission>
  private let expiresAt: Date

  init(permissions: Set<Permission>, expiresAt: Date) {
    self.remainingPermissions = permissions
    self.expiresAt = expiresAt
  }

  static func authorize(
    userMessage: String,
    precedingAssistantMessage: String?,
    now: Date = Date()
  ) -> PermissionRequestAuthorization? {
    guard !explicitlyRefusesPermission(userMessage) else {
      return nil
    }
    let directlyRequested = permissionsNamed(in: userMessage)
    if directlyRequested.count == 1, explicitlyRequestsPermission(userMessage) {
      return PermissionRequestAuthorization(
        permissions: directlyRequested,
        expiresAt: now.addingTimeInterval(authorizationLifetime)
      )
    }

    guard directlyRequested.isEmpty,
          isAffirmativeReply(userMessage),
          let precedingAssistantMessage,
          precedingAssistantRequestsPermission(precedingAssistantMessage),
          permissionsNamed(in: precedingAssistantMessage).count == 1
    else {
      return nil
    }

    return PermissionRequestAuthorization(
      permissions: permissionsNamed(in: precedingAssistantMessage),
      expiresAt: now.addingTimeInterval(authorizationLifetime)
    )
  }

  func consume(permissionType: String, now: Date = Date()) -> Bool {
    guard now <= expiresAt,
          let permission = Permission(rawValue: permissionType),
          remainingPermissions.remove(permission) != nil
    else {
      return false
    }
    return true
  }

  private static func permissionsNamed(in message: String) -> Set<Permission> {
    let normalized = normalize(message)
    return Set(Permission.allCases.filter { permission in
      permission.aliases.contains { containsPhrase($0, in: normalized) }
    })
  }

  private static func explicitlyRequestsPermission(_ message: String) -> Bool {
    let normalized = normalize(message)
    if containsPhrase("open", in: normalized)
      && (containsPhrase("settings", in: normalized) || containsPhrase("permission", in: normalized))
    {
      return true
    }
    return [
      "grant", "allow", "enable", "turn on", "open settings", "open the settings",
      "request", "ask for", "take me to", "show me the settings",
    ].contains { containsPhrase($0, in: normalized) }
  }

  private static func explicitlyRefusesPermission(_ message: String) -> Bool {
    let normalized = normalize(message)
    return ["do not", "don t", "dont", "not now", "never", "no thanks"].contains {
      containsPhrase($0, in: normalized)
    }
  }

  private static func isAffirmativeReply(_ message: String) -> Bool {
    let normalized = normalize(message)
    return [
      "yes", "yeah", "yep", "sure", "go ahead", "do it", "please do", "grant it", "allow it", "open it",
    ].contains(normalized)
  }

  private static func precedingAssistantRequestsPermission(_ message: String) -> Bool {
    let normalized = normalize(message)
    return containsPhrase("permission", in: normalized)
      && ["grant", "allow", "enable", "open", "settings", "need"].contains {
        containsPhrase($0, in: normalized)
      }
  }

  private static func containsPhrase(_ phrase: String, in normalized: String) -> Bool {
    let normalizedPhrase = normalize(phrase)
    return !normalizedPhrase.isEmpty && " \(normalized) ".contains(" \(normalizedPhrase) ")
  }

  private static func normalize(_ value: String) -> String {
    value
      .lowercased()
      .unicodeScalars
      .map { CharacterSet.alphanumerics.contains($0) ? String($0) : " " }
      .joined()
      .split(whereSeparator: \.isWhitespace)
      .joined(separator: " ")
  }
}
