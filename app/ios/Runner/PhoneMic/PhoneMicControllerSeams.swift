import AVFoundation
import Foundation

// Narrow dependency seams for the PhoneMic controller policy (SCA-491 / C5).
//
// The controller owns every capture lifecycle decision; these protocols are
// the ONLY things it touches outside its own file (plus the Pigeon contract
// types, which stay generated). Everything here compiles on macOS with plain
// `swiftc`, so the canonical phone-mic-native-events/v1 vectors replay
// through the PRODUCTION controller in
// `ios/test/phone_mic_lifecycle_replay_test.rb` with only OS audio/radio
// I/O faked. The live (app-target) wiring lives in PhoneMicHostApiImpl.swift.
//
// No policy lives in this file: signatures only.

/// Everything the controller emits toward Dart. The Pigeon
/// `PhoneMicFlutterApi` conforms via the live adapter; replay harnesses
/// record deliveries instead.
protocol PhoneMicEventSink: AnyObject {
    func onAudioFrame(pcm16leMono16k: Data, sessionId: Int64)
    func onStateChanged(state: PhoneMicCaptureState, sessionId: Int64)
    func onCaptureError(code: String, message: String, sessionId: Int64)
    func onBatchProgress(capturedSeconds: Double, sessionId: Int64)
}

/// The engine surface the controller drives. One instance per bring-up; the
/// real engine owns an AVAudioEngine input tap, the fake replays scripted
/// frames through the captured data sink.
protocol PhoneMicEngineControlling: AnyObject {
    var isRunning: Bool { get }

    /// The underlying AVAudioEngine for the interruption monitor's
    /// config-change observation, when one exists.
    var audioEngineForMonitor: AVAudioEngine? { get }

    func buildAndInstallTap(epoch: UInt64) throws
    func startEngine() throws
    func teardown()
}

/// Policy-neutral OS interruption signals. The production monitor adapts
/// AVFoundation/CallKit notifications onto this; replay harnesses fire them
/// from scripts on the controller's control queue.
enum PhoneMicInterruptionSignal {
    case interruptionBegan
    case interruptionEnded(shouldResume: Bool)
    case routeChanged(reasonDescription: String)
    case engineConfigChanged
    case mediaServicesReset
    case allCallsEnded
    case appBecameActive
}

protocol PhoneMicInterruptionSource: AnyObject {
    func startObserving()
    func stopObserving()
    func bindEngine(_ engine: AVAudioEngine?)
}

/// Microphone permission state (mirrors the AVAudioApplication/AVAudioSession
/// trichotomy; denied is surfaced as a start() error, never a dead session).
enum PhoneMicPermissionStatus {
    case granted
    case denied
    case undetermined
}

protocol PhoneMicPermissionChecking: AnyObject {
    func current() -> PhoneMicPermissionStatus
    /// Completion on an arbitrary thread; the controller hops back to its own queue.
    func request(_ completion: @escaping (Bool) -> Void)
}

/// Batch (Transcribe Later) opus pipeline. Created once per session at
/// bring-up, reused across rebuilds so the opus byte stream stays contiguous,
/// released only at stop/failStart.
protocol PhoneMicBatchEncoding: AnyObject {
    func encode(_ pcm: Data) -> [Data]
    /// Drop the sub-frame remainder so audio across a teardown is never spliced.
    func discardPartial()
}

protocol PhoneMicBatchWriting: AnyObject {
    func append(opusPackets: [Data], marker: String)
    /// Synchronous finalize + fsync + atomic promote; caller drains the audio queue first.
    func closeNowLocked(_ reason: String)
    var sessionFramesWritten: Int64 { get }
    func consumeStorageFullTransitionLocked() -> Bool
}

/// Every external effect the controller policy depends on, injected once at
/// init. `PhoneMicLiveEnvironment` (app target) wires the real AVAudioEngine
/// stack; replay harnesses inject fakes.
struct PhoneMicControllerEnvironment {
    var sink: PhoneMicEventSink
    var permission: PhoneMicPermissionChecking

    /// AVAudioSession category/activation (throws on failure).
    var configureSession: () throws -> Void
    var describeRoute: () -> String

    var makeMonitor: (
        _ controlQueue: DispatchQueue,
        _ onSignal: @escaping (PhoneMicInterruptionSignal) -> Void
    ) -> PhoneMicInterruptionSource?

    var makeEngine: (
        _ audioQueue: DispatchQueue,
        _ onConvertedData: @escaping (Data, UInt64) -> Void,
        _ onConvertError: @escaping (PhoneMicConverterPipeline.ConvertError, UInt64) -> Void
    ) -> PhoneMicEngineControlling

    // Batch-mode resources (dir + marker come from Dart-supplied settings).
    var batchDirectory: () -> String?
    var batchAutoMarker: () -> Bool
    var makeEncoder: () -> PhoneMicBatchEncoding?
    var makeWriter: (_ directory: String, _ audioQueue: DispatchQueue) -> PhoneMicBatchWriting
}
