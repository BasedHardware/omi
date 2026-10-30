import OmiService

extension AppEnvironment {
    /// A fresh voice session (onboarding, or recording the voice again from Settings).
    func makeVoiceIntro() -> VoiceIntroStore {
        let devices = devices
        let options = DebugLaunchOptions.current
        // Debug: with a pretend Omi, its "audio" is the injected file too.
        let fileForDevice = options.fakeDevice != nil ? options.captureAudioFile : nil
        return VoiceIntroStore(
            api: api,
            recognizer: AppleLiveRecognizer(fixtureTranscript: options.captureTranscript),
            phoneInput: PhoneVoiceInput(audioFile: options.captureAudioFile),
            deviceInput: {
                if let fileForDevice { return PhoneVoiceInput(audioFile: fileForDevice) }
                return DeviceVoiceInput(devices: devices)
            }
        )
    }
}
