import Foundation

/// Turns a finished turn's audio into its best available transcript.
///
/// Accuracy first, then availability: the backend's pre-recorded recognizer
/// (`/v2/voice-message/transcribe`, `velma-2` first) hears the whole utterance
/// with the on-screen vocabulary as context, and it is what a dictation is
/// transcribed with whenever it can be reached. The on-device Parakeet model —
/// already loaded for language identification — is the fallback, and with no
/// network it is the only recognizer there is. A turn never ends with nothing
/// while either can still answer.
///
/// The recognizers are injected so the order can be exercised without a
/// network or a model.
struct DictationTranscriber: Sendable {

  enum Source: String, Equatable, Sendable {
    case backend = "backend_batch_stt"
    case onDevice = "on_device_asr"
  }

  struct Result: Equatable, Sendable {
    let text: String
    let source: Source
  }

  /// How long the backend gets before the on-device model takes the turn. The
  /// user is holding nothing and watching nothing; a paste that lands late is
  /// a paste the user has already given up on.
  static let defaultBackendTimeout: TimeInterval = 12

  /// Whether a network path was available when the turn closed. Decided once,
  /// by the caller, so the order below is fixed for the whole transcription.
  var isOnline: Bool
  var backend: @Sendable (Data) async throws -> String?
  var onDevice: @Sendable (Data) async -> String?
  /// Called with a bounded reason whenever the backend was tried and the
  /// on-device model had to take over, so the switch is observable.
  var didFallBack: @Sendable (String) async -> Void = { _ in }
  var backendTimeout: TimeInterval = DictationTranscriber.defaultBackendTimeout

  /// Nil when nothing could transcribe the audio — or when the calling task
  /// was cancelled, in which case no fallback is tried either: a superseded
  /// turn must not keep working towards a paste.
  func transcribe(_ audio: Data) async -> Result? {
    guard !audio.isEmpty else { return nil }
    if isOnline {
      let backend = self.backend
      do {
        // Enforced at the boundary, not by cooperative cancellation alone: a
        // request stuck in a token refresh does not get to hold the key-up.
        let text = try await DeadlinedOperation.run(seconds: backendTimeout) { try await backend(audio) }
        if let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
          return Result(text: text, source: .backend)
        }
        await didFallBack("empty")
      } catch is CancellationError {
        return nil
      } catch DeadlinedOperation.Failure.timedOut {
        await didFallBack("timeout")
      } catch {
        await didFallBack("other")
      }
    }
    guard !Task.isCancelled else { return nil }
    guard let text = await onDevice(audio), !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return nil }
    return Result(text: text, source: .onDevice)
  }
}
