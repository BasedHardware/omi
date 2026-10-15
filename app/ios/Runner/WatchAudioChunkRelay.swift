import Foundation

/// Turns one Apple Watch audio chunk into the bytes Flutter's capture path expects.
///
/// Stateless on purpose: the iPhone keeps nothing about a Watch recording. Holding every chunk
/// until the last one (~115 MB per recorded hour) got the app killed on long sessions (#20479).
enum WatchAudioChunkRelay {
    /// Returns the chunk with the 3 header bytes downstream strips, or nil for the Watch's empty
    /// end-of-recording marker.
    static func flutterPayload(for chunk: Data) -> Data? {
        guard !chunk.isEmpty else { return nil }
        var prefixed = Data([0x00, 0x00, 0x00])
        prefixed.append(chunk)
        return prefixed
    }
}
