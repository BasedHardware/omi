import Foundation

/// A live source of PCM audio.
///
/// Every implementation delivers the same wire shape, so the transcriber never has to know
/// where audio came from: **16 kHz mono Int16 little-endian PCM**. Anything else is a bug in
/// the source, not something downstream is allowed to compensate for.
protocol AudioSource: AnyObject {
    /// Chunks are 16 kHz mono Int16 little-endian PCM.
    func start(onChunk: @escaping @Sendable (Data) -> Void, onLevel: @escaping @Sendable (Float) -> Void) async throws
    func stop()
    var isRunning: Bool { get }
}

enum AudioCaptureError: LocalizedError {
    /// No CoreAudio device with input channels is available.
    case noInputDevice
    /// The device reported no usable stream format, or no converter to 16 kHz could be built.
    case formatUnavailable
    /// `AudioDeviceCreateIOProcIDWithBlock` / `AudioDeviceStart` failed.
    case ioProcFailed(OSStatus)
    /// `AudioHardwareCreateProcessTap` failed (system audio).
    case tapFailed(OSStatus)
    /// The private aggregate device carrying the tap could not be created (system audio).
    case aggregateFailed(OSStatus)

    var errorDescription: String? {
        switch self {
        case .noInputDevice:
            return "No audio input device is available"
        case .formatUnavailable:
            return "The audio device did not report a usable format"
        case .ioProcFailed(let status):
            return "CoreAudio refused to start the input device (\(status))"
        case .tapFailed(let status):
            return "System audio tap could not be created (\(status))"
        case .aggregateFailed(let status):
            return "System audio aggregate device could not be created (\(status))"
        }
    }
}
