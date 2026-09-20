import AVFoundation
import Flutter
import Foundation

/// Pigeon adapter: forwards host-API calls to the controller. No logic lives
/// here — the controller hops to its own queue and dispatches completions back
/// to the main thread itself.
final class PhoneMicHostApiImpl: PhoneMicHostApi {
    private let controller: PhoneMicController

    init(controller: PhoneMicController) {
        self.controller = controller
    }

    func start(mode: PhoneMicCaptureMode, sessionId: Int64, completion: @escaping (Result<Void, Error>) -> Void) {
        controller.start(mode: mode, sessionId: sessionId, completion: completion)
    }

    func stop(completion: @escaping (Result<Void, Error>) -> Void) {
        controller.stop {
            completion(.success(()))
        }
    }

    func isRecording() throws -> Bool {
        return controller.isRecording
    }
}

// MARK: - Live environment wiring (app target)
//
// The production implementations of the controller seams: the Pigeon sink,
// the AVAudioEngine stack, the OS permission/session/monitor surfaces and the
// opus batch pipeline. The replay harness compiles the controller against
// fakes instead (ios/test/phone_mic_lifecycle_replay_test.rb) — nothing in
// this file is policy.

extension PhoneMicFlutterApi: PhoneMicEventSink {
    func onAudioFrame(pcm16leMono16k: Data, sessionId: Int64) {
        onAudioFrame(pcm16leMono16k: FlutterStandardTypedData(bytes: pcm16leMono16k), sessionId: sessionId) { _ in }
    }

    func onStateChanged(state: PhoneMicCaptureState, sessionId: Int64) {
        onStateChanged(state: state, sessionId: sessionId) { _ in }
    }

    func onCaptureError(code: String, message: String, sessionId: Int64) {
        onCaptureError(code: code, message: message, sessionId: sessionId) { _ in }
    }

    func onBatchProgress(capturedSeconds: Double, sessionId: Int64) {
        onBatchProgress(capturedSeconds: capturedSeconds, sessionId: sessionId) { _ in }
    }
}

extension PhoneMicCaptureEngine: PhoneMicEngineControlling {
    var audioEngineForMonitor: AVAudioEngine? { engine }
}

extension PhoneMicInterruptionMonitor: PhoneMicInterruptionSource {
    func bindEngine(_ engine: AVAudioEngine?) {
        guard let engine else { return }
        bindEngine(engine)
    }
}

extension PhoneMicOpusEncoder: PhoneMicBatchEncoding {}

extension PhoneMicBatchAudioWriter: PhoneMicBatchWriting {}
private final class PhoneMicLivePermission: PhoneMicPermissionChecking {
    func current() -> PhoneMicPermissionStatus {
        switch PhoneMicPermissionGate.current() {
        case .granted: return .granted
        case .denied: return .denied
        case .undetermined: return .undetermined
        }
    }

    func request(_ completion: @escaping (Bool) -> Void) {
        PhoneMicPermissionGate.request(completion)
    }
}

enum PhoneMicLiveEnvironment {
    /// The production controller environment: real AVAudioSession/Engine,
    /// OS permission gate, OS interruption monitor, opus batch pipeline.
    static func make(sink: PhoneMicEventSink) -> PhoneMicControllerEnvironment {
        PhoneMicControllerEnvironment(
            sink: sink,
            permission: PhoneMicLivePermission(),
            configureSession: { try PhoneMicSessionConfigurator.configureAndActivate() },
            describeRoute: { PhoneMicSessionConfigurator.describeCurrentRoute() },
            makeMonitor: { controlQueue, onSignal in
                PhoneMicInterruptionMonitor(controlQueue: controlQueue) { event in
                    switch event {
                    case .interruptionBegan:
                        onSignal(.interruptionBegan)
                    case .interruptionEnded(let shouldResume):
                        onSignal(.interruptionEnded(shouldResume: shouldResume))
                    case .routeChanged(let reason):
                        onSignal(.routeChanged(reasonDescription: "\(reason.rawValue)"))
                    case .engineConfigChanged:
                        onSignal(.engineConfigChanged)
                    case .mediaServicesReset:
                        onSignal(.mediaServicesReset)
                    case .allCallsEnded:
                        onSignal(.allCallsEnded)
                    case .appBecameActive:
                        onSignal(.appBecameActive)
                    }
                }
            },
            makeEngine: { audioQueue, onConvertedData, onConvertError in
                PhoneMicCaptureEngine(
                    audioQueue: audioQueue,
                    onConvertedData: onConvertedData,
                    onConvertError: onConvertError
                )
            },
            batchDirectory: {
                let dir = UserDefaults.standard.string(forKey: "flutter.batchAudioDir")
                return (dir?.isEmpty == false) ? dir : nil
            },
            batchAutoMarker: { UserDefaults.standard.bool(forKey: "flutter.phoneBatchAuto") },
            makeEncoder: { PhoneMicOpusEncoder() },
            makeWriter: { directory, audioQueue in
                PhoneMicBatchAudioWriter(dir: directory, queue: audioQueue)
            }
        )
    }
}
