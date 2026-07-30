import Foundation

/// Shared STT engine identifiers (parity with Python/RN/device SDKs).
public enum OmiSttEngine: String, Sendable {
  case deepgram
  case whisper
  case parakeet
}

public protocol OmiStreamingTranscriber: AnyObject {
  /// Push PCM16 LE mono @ 16 kHz.
  func appendPcm(_ data: Data)
  func stop()
}

public typealias OmiTranscriptHandler = @Sendable (String) -> Void
