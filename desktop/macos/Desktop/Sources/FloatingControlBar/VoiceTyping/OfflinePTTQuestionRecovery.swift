import AppKit
import Combine
import Foundation

/// One unsent question, kept briefly in memory after local transcription while offline.
/// Recovery is explicit: it never retries a request or writes to the chat journal.
@MainActor
final class OfflinePTTQuestionRecovery: ObservableObject {
  static let shared = OfflinePTTQuestionRecovery()

  private struct Question {
    let id = UUID()
    let text: String
    let authorization: RuntimeOwnerAuthorizationSnapshot
    let expiresAt: Date
  }

  @Published private(set) var hasQuestion = false
  private var question: Question?
  private let now: () -> Date
  private let isAuthorized: (RuntimeOwnerAuthorizationSnapshot) -> Bool
  private let sleep: @Sendable (TimeInterval) async throws -> Void
  private var expiryTask: Task<Void, Never>?

  init(
    now: @escaping () -> Date = Date.init,
    isAuthorized: @escaping (RuntimeOwnerAuthorizationSnapshot) -> Bool = RuntimeOwnerIdentity.isAuthorizationCurrent,
    sleep: @escaping @Sendable (TimeInterval) async throws -> Void = { try await Task.sleep(for: .seconds($0)) }
  ) {
    self.now = now
    self.isAuthorized = isAuthorized
    self.sleep = sleep
  }

  deinit { expiryTask?.cancel() }

  var isAvailable: Bool { validQuestion != nil }

  @discardableResult
  func capture(_ text: String, authorization: RuntimeOwnerAuthorizationSnapshot) -> Bool {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty, isAuthorized(authorization) else { return false }
    clear()
    let captured = Question(text: trimmed, authorization: authorization, expiresAt: now().addingTimeInterval(300))
    question = captured
    hasQuestion = true
    let sleep = sleep
    expiryTask = Task { @MainActor [weak self] in
      do { try await sleep(300) } catch { return }
      guard !Task.isCancelled, self?.question?.id == captured.id else { return }
      self?.clear()
    }
    return true
  }

  func clear() {
    expiryTask?.cancel()
    expiryTask = nil
    question = nil
    hasQuestion = false
  }

  /// The destination merges with its own restored draft when it mounts.
  @discardableResult
  func review(present: (String, RuntimeOwnerAuthorizationSnapshot) -> Bool) -> Bool {
    guard let question = validQuestion else {
      clear()
      return false
    }
    guard present(question.text, question.authorization) else { return false }
    clear()
    return true
  }

  @discardableResult
  func copy(write: (String) -> Void) -> Bool {
    guard let question = validQuestion else {
      clear()
      return false
    }
    write(question.text)
    return true
  }

  func reviewInMainChat() {
    _ = review { text, authorization in
      guard let target = AppDelegate.summonWindowTarget() else { return false }
      target.openMainAppChat(appendingDraft: text, authorization: authorization)
      return true
    }
  }

  func copyToClipboard() {
    _ = copy { text in
      NSPasteboard.general.clearContents()
      NSPasteboard.general.setString(text, forType: .string)
    }
  }

  private var validQuestion: Question? {
    guard let question, now() < question.expiresAt, isAuthorized(question.authorization) else { return nil }
    return question
  }
}
