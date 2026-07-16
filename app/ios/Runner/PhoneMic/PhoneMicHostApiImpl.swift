import Foundation

/// Pigeon adapter: forwards host-API calls to the controller. No logic lives
/// here — the controller hops to its own queue and dispatches completions back
/// to the main thread itself.
final class PhoneMicHostApiImpl: PhoneMicHostApi {
    private let controller: PhoneMicController

    init(controller: PhoneMicController) {
        self.controller = controller
    }

    func start(mode: PhoneMicCaptureMode, completion: @escaping (Result<Void, Error>) -> Void) {
        controller.start(mode: mode, completion: completion)
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
