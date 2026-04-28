# Android Audio Limitations

Android controls microphone priority. When another app has priority, Android may silence, deprioritize, or otherwise degrade Omi's microphone capture. This is expected platform behavior and must not be bypassed.

Advanced Ambient Capture detects degraded capture using:

- `AudioManager.registerAudioRecordingCallback`
- `AudioRecordingConfiguration.isClientSilenced` where available
- `AudioManager.mode`
- RMS / dBFS
- zero-frame percentage
- sustained silence duration

Call audio is protected by Android platform rules. Omi does not claim guaranteed call recording and does not attempt privileged, root, or spyware behavior.

Accessibility mode is optional and user-enabled. It improves foreground-app awareness and can observe visible caption/transcript text only when caption fallback is explicitly enabled.
