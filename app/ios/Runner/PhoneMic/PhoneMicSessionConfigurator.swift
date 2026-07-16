import AVFoundation

/// Idempotent AVAudioSession setup for phone-mic capture.
///
/// Reads the current configuration back and only calls setCategory when
/// something actually differs: flutter_sound (chat voice memos) and just_audio
/// (playback) share this session and reconfigure it between captures, and a
/// gratuitous setCategory can itself drop the active input route.
///
/// Never deactivates the session. Other Omi audio may still be using it, and
/// with .mixWithOthers our activation is non-destructive to other apps, so
/// leaving it active after capture stops is harmless.
///
/// No setPreferredSampleRate / setPreferredIOBufferDuration / setPreferredInput:
/// the capture engine adopts whatever format the hardware/route negotiates and
/// resamples downstream, which avoids fighting the OS across route changes.
enum PhoneMicSessionConfigurator {
    static let category: AVAudioSession.Category = .playAndRecord
    static let mode: AVAudioSession.Mode = .default
    /// .mixWithOthers: recording must not stop the user's music/podcasts.
    /// Bluetooth options keep AirPods/headset mics routable, matching the
    /// behavior of the previous flutter_sound-based capture path.
    /// .defaultToSpeaker: this session stays active after capture stops (we
    /// never deactivate a shared session) and the app's players do no session
    /// configuration of their own — without this option, playAndRecord routes
    /// subsequent in-app playback to the earpiece receiver, which users hear
    /// as near-silent audio.
    static let options: AVAudioSession.CategoryOptions = [
        .mixWithOthers, .allowBluetoothHFP, .allowBluetoothA2DP, .defaultToSpeaker,
    ]

    static func configureAndActivate() throws {
        let session = AVAudioSession.sharedInstance()
        if session.category != category || session.mode != mode || session.categoryOptions != options {
            try session.setCategory(category, mode: mode, options: options)
        }
        // Hardening: UI haptics and system sounds must not disturb the record
        // route, and system alerts should not interrupt an ongoing capture.
        // Both are best-effort — failure to set them never blocks capture.
        try? session.setAllowHapticsAndSystemSoundsDuringRecording(true)
        try? session.setPrefersNoInterruptionsFromSystemAlerts(true)
        try session.setActive(true)
    }

    static func describeCurrentRoute() -> String {
        let route = AVAudioSession.sharedInstance().currentRoute
        let inputs = route.inputs.map { "\($0.portType.rawValue):\($0.portName)" }.joined(separator: ",")
        let outputs = route.outputs.map { $0.portType.rawValue }.joined(separator: ",")
        return "in=[\(inputs)] out=[\(outputs)]"
    }
}
