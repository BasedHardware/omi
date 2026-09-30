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
    /// The conversation id is not known yet (force-process, `/from-segments`): only the OCR flush
    /// ran. Expected, so it records nothing.
    case unbound
    /// The side-effect-free window read failed. Degraded: the retry or the note view covers it.
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
    /// Which pass degraded, and what now covers it: before notes the post-finalize retry does;
    /// after `/from-segments` creation only the note view's retry on open is left.
    var from = "before_notes"
    var to = "after_finalize"

    /// The bounded fallback reason for a pass that settled in failure, or nil if it did not fail.
    static func reason(for outcome: Outcome) -> String? {
      switch outcome {
      case .timedOut: return "timeout"
      case .conversationUnavailable: return "other"
      // An unsealed Rewind chunk is not an upload failure; keep the two apart in the bucket.
      case .settled(.failed(let detail)):
        return detail == MeetingScreenshotsStore.activeChunkRetryDetail ? "other" : "upload_failed"
      default: return nil
      }
    }
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
    flushScreenActivity: {
      // Drain within the pass bound; whatever is left ships on the periodic path.
      let seconds = Double(defaultTimeout.components.seconds)
      await ScreenActivitySyncService.shared.flushMeetingWindow($0, deadline: Date().addingTimeInterval(seconds))
    },
    adjudicate: { @MainActor conversationID, window in
      // A fresh store shares the static cache and in-flight map with every note view, so this is
      // the same run a note opened mid-flight awaits, and its result is what that note renders.
      await MeetingScreenshotsStore().loadAndWait(conversationID: conversationID, selectionWindow: window)
    },
    sleep: { try? await Task.sleep(for: $0) },
    recordFallback: { fallback in
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "meeting_screen_evidence",
        from: fallback.from,
        to: fallback.to,
        reason: fallback.reason,
        outcome: .degraded)
    })

  /// Before the backend writes notes: flush the meeting's OCR text and, when the conversation id
  /// is known, select and adjudicate its frames. Returns within `timeout`.
  func beforeNotes(
    captureInterval: DateInterval,
    conversationID: String?,
    fetchSelectionWindow: (@Sendable () async throws -> MeetingScreenshotSelectionWindow?)?
  ) async -> Outcome {
    let enabled = await screenshotsEnabled()
    let pass = self
    let outcome = await Self.first(
      of: {
        async let flushed: Void = pass.flushScreenActivity(captureInterval)
        let outcome: Outcome
        if !enabled {
          outcome = .disabled
        } else if let conversationID, let fetchSelectionWindow {
          outcome = await pass.adjudicate(conversationID: conversationID, fetchSelectionWindow: fetchSelectionWindow)
        } else {
          outcome = .unbound
        }
        await flushed
        return outcome
      },
      orAfter: timeout,
      sleep: sleep,
      timeoutValue: .timedOut)
    log("MeetingScreenEvidence: before-notes pass for \(conversationID ?? "unbound") -> \(outcome)")
    if !enabled {
      // Only the OCR flush ran; a late flush is worth telemetry but never a screenshot retry.
      if outcome == .timedOut { recordFallback(Fallback(reason: "timeout")) }
      return .disabled
    }
    if let reason = Fallback.reason(for: outcome) {
      recordFallback(Fallback(reason: reason))
    }
    return outcome
  }

  /// After the backend has finalized a cloud conversation whose pre-notes pass did not settle:
  /// adjudicate again so screenshots exist on every surface even if the note is never opened on
  /// this Mac. A run the bound left in flight is joined through the store, never repeated.
  func afterFinalize(
    conversationID: String,
    fetchSelectionWindow: @Sendable () async throws -> MeetingScreenshotSelectionWindow?
  ) async -> Outcome {
    guard await screenshotsEnabled() else { return .disabled }
    let outcome = await adjudicate(conversationID: conversationID, fetchSelectionWindow: fetchSelectionWindow)
    log("MeetingScreenEvidence: after-finalize pass for \(conversationID) -> \(outcome)")
    if let reason = Fallback.reason(for: outcome) {
      // The last automatic attempt: only the note view's retry on open is left.
      recordFallback(Fallback(reason: reason, from: "after_finalize", to: "note_open"))
    }
    return outcome
  }

  /// After `/from-segments` has already written the notes: adjudicate so screenshots exist on
  /// every surface. Unbounded on purpose — nothing waits for it.
  func afterCreation(conversation: ServerConversation) async -> Outcome {
    guard await screenshotsEnabled() else { return .disabled }
    guard let window = MeetingScreenshotSelectionWindow.resolve(conversation) else { return .untrustedWindow }
    let outcome = Outcome.settled(await adjudicate(conversation.id, window))
    log("MeetingScreenEvidence: after-creation pass for \(conversation.id) -> \(outcome)")
    if let reason = Fallback.reason(for: outcome) {
      // Nothing awaits this pass, so its failure would otherwise be silent to operators too.
      recordFallback(Fallback(reason: reason, from: "after_creation", to: "note_open"))
    }
    return outcome
  }

  private func adjudicate(
    conversationID: String,
    fetchSelectionWindow: @Sendable () async throws -> MeetingScreenshotSelectionWindow?
  ) async -> Outcome {
    // The server's own trusted window, from a side-effect-free read: this pass runs for notes
    // nobody has opened, so it must never trigger first-open work. Nil (no trusted window yet, or a
    // server that predates the field) leaves the note view to adjudicate on open.
    let window: MeetingScreenshotSelectionWindow?
    do {
      window = try await fetchSelectionWindow()
    } catch {
      return .conversationUnavailable
    }
    guard let window else { return .untrustedWindow }
    return .settled(await adjudicate(conversationID, window))
  }

  /// The side-effect-free window read: `GET /v1/conversations/{id}/screenshots`.
  static func serverSelectionWindow(
    conversationID: String, client: APIClient
  ) async throws -> MeetingScreenshotSelectionWindow? {
    try await client.getConversationScreenFrames(conversationID: conversationID).trustedSelectionFingerprint
      .flatMap(MeetingScreenshotSelectionWindow.init(serverFingerprint:))
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
