import Foundation

/// Maps transport and system failures into concise copy for non-chat UI.
///
/// Chat and agent transcripts deliberately keep their richer error context. This
/// mapper is only for app chrome outside active chat and agent transcripts, such
/// as dashboards, pages, sheets, and alerts, where a raw server detail or
/// decoding failure is distracting and unhelpful.
enum UserFacingErrorPresentation {
  enum Context {
    case dashboard
    case chatSessions
    case conversations
    case conversationSearch
    case conversationMerge
    case tasks
    case memories
    case memoryVisibility
    case memoryDeletion
    case screenshots
    case goals
    case persona
    case signIn
    case onboarding
    case integration(String)
    case browserExtension
    case memoryExport
    case storageSync
    case transcription
    case accountDeletion

    fileprivate var action: String {
      switch self {
      case .dashboard: return "refresh the dashboard"
      case .chatSessions: return "load chats"
      case .conversations: return "load conversations"
      case .conversationSearch: return "search conversations"
      case .conversationMerge: return "merge conversations"
      case .tasks: return "update tasks"
      case .memories: return "load memories"
      case .memoryVisibility: return "update memory visibility"
      case .memoryDeletion: return "delete memories"
      case .screenshots: return "load screenshots"
      case .goals: return "load goals"
      case .persona: return "load your persona"
      case .signIn: return "sign in"
      case .onboarding: return "save that step"
      case .integration(let name): return "connect to \(name)"
      case .browserExtension: return "connect the browser extension"
      case .memoryExport: return "prepare that export"
      case .storageSync: return "sync device storage"
      case .transcription: return "start transcription"
      case .accountDeletion: return "delete your account"
      }
    }

    fileprivate var isSignIn: Bool {
      if case .signIn = self { return true }
      return false
    }
  }

  static func message(for error: Error, while context: Context) -> String {
    if let apiError = error as? APIError {
      switch apiError {
      case .httpError(let statusCode, _):
        switch statusCode {
        case 401:
          return context.isSignIn
            ? "Couldn't sign in. Try again."
            : "Please sign in again, then try once more."
        case 403:
          return "You don't have permission to do that."
        case 409:
          return "This changed while Omi was updating. Refresh and try again."
        case 429:
          return "Omi is busy right now. Try again in a moment."
        case 500...599:
          return "Omi's service is unavailable right now. Try again."
        default:
          return fallback(for: context)
        }
      case .invalidResponse, .decodingError:
        return "Omi received an unexpected response. Try again."
      case .syncRateLimited:
        return "Omi is busy right now. Try again in a moment."
      case .unsupportedTierScopedBulkMutation:
        return "That option isn't available yet."
      case .syncUploadRejected:
        return fallback(for: context)
      case .unauthorized:
        return context.isSignIn
          ? "Couldn't sign in. Try again."
          : "Please sign in again, then try once more."
      }
    }

    if let urlError = error as? URLError {
      switch urlError.code {
      case .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed, .networkConnectionLost,
        .notConnectedToInternet, .timedOut:
        return "Check your connection and try again."
      default:
        return fallback(for: context)
      }
    }

    return fallback(for: context)
  }

  /// Sanitizes already-materialized error copy at display time when the original
  /// `Error` is not available (for example, values stored on invariant-owned types).
  static func message(from raw: String, while context: Context) -> String {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return fallback(for: context) }
    if shouldPreserveCuratedCopy(trimmed) {
      return trimmed
    }
    return fallback(for: context)
  }

  private static func shouldPreserveCuratedCopy(_ text: String) -> Bool {
    let lowered = text.lowercased()
    if text.count > 160 { return false }
    if text.contains("://") || text.contains("Error Domain=") { return false }
    if lowered.contains("nsurlerror") || lowered.contains("cfstream") { return false }
    if lowered.range(of: #"\b[45]\d{2}\b"#, options: .regularExpression) != nil { return false }
    if text.filter({ $0 == ":" }).count > 1 { return false }
    if lowered.hasPrefix("omi ") || lowered.hasPrefix("couldn't ") || lowered.hasPrefix("didn't ") {
      return true
    }
    return text.hasSuffix(".") && text.count < 120
  }

  private static func fallback(for context: Context) -> String {
    "Couldn't \(context.action). Try again."
  }
}
