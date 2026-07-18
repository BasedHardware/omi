import AVFoundation

/// Microphone permission, availability-gated: AVAudioApplication on iOS 17+,
/// the older AVAudioSession API below (deployment target is iOS 16). Denial is
/// surfaced as a thrown start() error, never a silently dead recording.
enum PhoneMicPermissionGate {
    enum Status {
        case granted
        case denied
        case undetermined
    }

    static func current() -> Status {
        if #available(iOS 17.0, *) {
            switch AVAudioApplication.shared.recordPermission {
            case .granted: return .granted
            case .undetermined: return .undetermined
            case .denied: return .denied
            @unknown default: return .denied
            }
        } else {
            switch AVAudioSession.sharedInstance().recordPermission {
            case .granted: return .granted
            case .undetermined: return .undetermined
            case .denied: return .denied
            @unknown default: return .denied
            }
        }
    }

    /// The completion is invoked on an arbitrary thread; callers hop back to
    /// their own queue.
    static func request(_ completion: @escaping (Bool) -> Void) {
        if #available(iOS 17.0, *) {
            AVAudioApplication.requestRecordPermission { granted in
                completion(granted)
            }
        } else {
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                completion(granted)
            }
        }
    }
}
