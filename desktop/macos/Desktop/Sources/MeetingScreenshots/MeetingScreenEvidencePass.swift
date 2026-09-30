//
//  MeetingScreenEvidencePass.swift — screen evidence for a meeting, gathered once, before notes.
//
//  Notes used to be written first and screenshots chosen later, lazily, when someone opened the
//  note — so nothing the judge saw could ever reach the notes. This runs the same pipeline the note
//  view runs (`MeetingScreenshotsStore`: on-device selection, then `MeetingFrameJudge`) at meeting
//  finalization, before the backend is asked to process the conversation, and flushes the meeting's
//  OCR text so the backend's screen-text digest sees the end of the call.
//
//  It is evidence, never a gate. The whole pass is bounded by `timeout`; when the bound expires,
//  finalization proceeds and whatever is still running keeps running in the background, where a
//  note opened meanwhile joins it through the store's shared in-flight map instead of starting a
//  second adjudication. Every failure — no network, a 409 because egress is off, an untrusted
//  window — is silent here and leaves the note view to retry on open, exactly as before.
//

import Foundation

struct MeetingScreenEvidencePass: Sendable {
  enum Outcome: Equatable, Sendable {
    /// Meeting screenshots are switched off for this account.
    case disabled
    /// The conversation's transcript does not yet give a window the server would trust.
    case untrustedWindow
    case conversationUnavailable
    case settled(MeetingScreenshotsStore.Phase)
    /// The bound expired first; the work continues in the background.
    case timedOut

    /// Whether the conversation still lacks a settled screenshot pass after this outcome, so the
    /// post-finalization retry should run. An untrusted pre-finalization window can become trusted
    /// once the backend stamps `finished_at`, so it is retried too.
    var needsRetryAfterFinalize: Bool {
      switch self {
      case .disabled, .settled(.ready), .settled(.noCapture), .settled(.disabled): return false
      default: return true
      }
    }
  }

  /// A degraded fail-open path taken before notes (`fallback-telemetry.md`): notes proceed without
  /// the evidence and the post-finalization retry takes over. Bounded labels only.
  struct Fallback: Equatable, Sendable {
    let reason: String
  }

  /// Long enough for the server's serial judge over the eight-candidate ceiling on a normal link;
  /// short enough that a meeting's notes are never held hostage by screen evidence.
  static let defaultTimeout: Duration = .seconds(20)

  var timeout: Duration = Self.defaultTimeout
  var screenshotsEnabled: @Sendable () async -> Bool
  var flushScreenActivity: @Sendable (DateInterval) async -> Void
  var adjudicate: @Sendable (String, MeetingScreenshotSelectionWindow) async -> MeetingScreenshotsStore.Phase
  var sleep: @Sendable (Duration) async -> Void
  var recordFallback: @Sendable (Fallback) -> Void = { _ in }

  static let production = MeetingScreenEvidencePass(
    screenshotsEnabled: { MeetingNoteScreenshotsFeature.isEnabled },
    flushScreenActivity: { await ScreenActivitySyncService.shared.flushMeetingWindow($0) },
    adjudicate: { @MainActor conversationID, window in
      // A fresh store shares the static cache and in-flight map with every note view, so this is
      // the same run a note opened mid-flight awaits, and its result is what that note renders.
      await MeetingScreenshotsStore().loadAndWait(conversationID: conversationID, selectionWindow: window)
    },
    sleep: { try? await Task.sleep(for: $0) },
    recordFallback: { fallback in
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "meeting_screen_evidence",
        from: "before_notes",
        to: "after_finalize",
        reason: fallback.reason,
        outcome: .degraded)
    })

  /// Before the backend writes notes: flush the meeting's OCR text and, when the conversation id
  /// is known, select and adjudicate its frames. Returns within `timeout`.
  func beforeNotes(
    captureInterval: DateInterval,
    conversationID: String?,
    fetchConversation: (@Sendable () async throws -> ServerConversation)?
  ) async -> Outcome {
    let enabled = await screenshotsEnabled()
    let pass = self
    let outcome = await Self.first(
      of: {
        async let flushed: Void = pass.flushScreenActivity(captureInterval)
        let outcome: Outcome
        if !enabled {
          outcome = .disabled
        } else if let conversationID, let fetchConversation {
          outcome = await pass.adjudicate(conversationID: conversationID, fetchConversation: fetchConversation)
        } else {
          outcome = .conversationUnavailable
        }
        await flushed
        return outcome
      },
      orAfter: timeout,
      sleep: sleep,
      timeoutValue: .timedOut)
    log("MeetingScreenEvidence: before-notes pass for \(conversationID ?? "unbound") -> \(outcome)")
    switch outcome {
    case .timedOut:
      recordFallback(Fallback(reason: "timeout"))
    case .settled(.failed):
      recordFallback(Fallback(reason: "upload_failed"))
    default:
      break
    }
    return outcome
  }

  /// After the backend has finalized a cloud conversation whose pre-notes pass did not settle:
  /// adjudicate again so screenshots exist on every surface even if the note is never opened on
  /// this Mac. A run the bound left in flight is joined through the store, never repeated.
  func afterFinalize(
    conversationID: String,
    fetchConversation: @Sendable () async throws -> ServerConversation
  ) async -> Outcome {
    guard await screenshotsEnabled() else { return .disabled }
    let outcome = await adjudicate(conversationID: conversationID, fetchConversation: fetchConversation)
    log("MeetingScreenEvidence: after-finalize pass for \(conversationID) -> \(outcome)")
    return outcome
  }

  /// After `/from-segments` has already written the notes: adjudicate so screenshots exist on
  /// every surface. Unbounded on purpose — nothing waits for it.
  func afterCreation(conversation: ServerConversation) async -> Outcome {
    guard await screenshotsEnabled() else { return .disabled }
    guard let window = MeetingScreenshotSelectionWindow.resolve(conversation) else { return .untrustedWindow }
    let outcome = Outcome.settled(await adjudicate(conversation.id, window))
    log("MeetingScreenEvidence: after-creation pass for \(conversation.id) -> \(outcome)")
    return outcome
  }

  private func adjudicate(
    conversationID: String,
    fetchConversation: @Sendable () async throws -> ServerConversation
  ) async -> Outcome {
    guard let conversation = try? await fetchConversation() else { return .conversationUnavailable }
    // The same resolver the note view uses, over the same server document, so the fingerprint the
    // server stamps is the one the note later asks for.
    guard let window = MeetingScreenshotSelectionWindow.resolve(conversation) else { return .untrustedWindow }
    return .settled(await adjudicate(conversationID, window))
  }

  /// The first of `work` or the bound. `work` is not cancelled when the bound wins: it runs to
  /// completion in the background so its result still lands in the shared cache.
  static func first<T: Sendable>(
    of work: @escaping @Sendable () async -> T,
    orAfter timeout: Duration,
    sleep: @escaping @Sendable (Duration) async -> Void,
    timeoutValue: T
  ) async -> T {
    await withCheckedContinuation { continuation in
      let gate = ResumeOnce(continuation)
      let timer = Task {
        await sleep(timeout)
        gate.resume(timeoutValue)
      }
      Task {
        let value = await work()
        // Resume before cancelling: a cancelled sleep returns early, and its resume must lose.
        gate.resume(value)
        timer.cancel()
      }
    }
  }
}

private final class ResumeOnce<T: Sendable>: @unchecked Sendable {
  private let lock = NSLock()
  private var continuation: CheckedContinuation<T, Never>?

  init(_ continuation: CheckedContinuation<T, Never>) {
    self.continuation = continuation
  }

  func resume(_ value: T) {
    lock.lock()
    let pending = continuation
    continuation = nil
    lock.unlock()
    pending?.resume(returning: value)
  }
}
