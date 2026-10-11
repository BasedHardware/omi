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

  enum UnavailableReason: String, Equatable, Sendable {
    case emptyAudio = "empty_audio"
    case noTranscript = "no_transcript"
    case onDeviceTimedOut = "on_device_transcription_timeout"
  }

  enum Outcome: Equatable, Sendable {
    case transcribed(Result)
    case unavailable(UnavailableReason)
    case cancelled
  }

  /// How long the backend gets before the on-device model takes the turn. The
  /// user is holding nothing and watching nothing; a paste that lands late is
  /// a paste the user has already given up on.
  static let defaultBackendTimeout: TimeInterval = 12
  /// The local decoder is normally much faster than the remote recognizer, but
  /// its first model load can stall. Keep the same user-facing ceiling so an
  /// offline turn cannot hold the caret (or an automation client) forever.
  static let defaultOnDeviceTimeout: TimeInterval = 12

  /// Whether a network path was available when the turn closed. Decided once,
  /// by the caller, so the order below is fixed for the whole transcription.
  var isOnline: Bool
  var backend: @Sendable (Data) async throws -> String?
  var onDevice: @Sendable (Data) async -> String?
  /// Called with a bounded reason whenever the backend was tried and the
  /// on-device model had to take over, so the switch is observable.
  var didFallBack: @Sendable (String) async -> Void = { _ in }
  var backendTimeout: TimeInterval = DictationTranscriber.defaultBackendTimeout
  var onDeviceTimeout: TimeInterval = DictationTranscriber.defaultOnDeviceTimeout

  /// Detailed result for owners that must distinguish an ordinary empty
  /// decode from a recognizer that exceeded its liveness contract.
  func outcome(for audio: Data) async -> Outcome {
    guard !audio.isEmpty else { return .unavailable(.emptyAudio) }
    if isOnline {
      let backend = self.backend
      do {
        // Enforced at the boundary, not by cooperative cancellation alone: a
        // request stuck in a token refresh does not get to hold the key-up.
        let text = try await DeadlinedOperation.run(seconds: backendTimeout) { try await backend(audio) }
        if let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
          return .transcribed(Result(text: text, source: .backend))
        }
        await didFallBack("empty")
      } catch is CancellationError {
        return .cancelled
      } catch DeadlinedOperation.Failure.timedOut {
        await didFallBack("timeout")
      } catch {
        await didFallBack("other")
      }
    }
    guard !Task.isCancelled else { return .cancelled }
    let onDevice = self.onDevice
    do {
      // Enforce this at the same non-cooperative boundary as backend STT. A
      // model download/load can ignore cancellation; DeadlinedOperation still
      // returns now and drops that task's eventual text instead of pasting it
      // after the user or harness has moved on.
      let text = try await DeadlinedOperation.run(seconds: onDeviceTimeout) {
        await onDevice(audio)
      }
      guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else { return .unavailable(.noTranscript) }
      return .transcribed(Result(text: text, source: .onDevice))
    } catch is CancellationError {
      return .cancelled
    } catch DeadlinedOperation.Failure.timedOut {
      return .unavailable(.onDeviceTimedOut)
    } catch {
      return .unavailable(.noTranscript)
    }
  }
}
