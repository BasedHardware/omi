# Advanced Ambient Capture

Advanced Ambient Capture is an optional Android-only experimental mode that lets the phone microphone feed the same Omi audio, WAL, sync, and transcription pipeline used by normal phone mic capture.

The feature is disabled by default. Users must enable it under Developer / Experimental Settings before native Android capture can start. While active, Android always shows the microphone privacy indicator and Omi always shows a persistent foreground-service notification with Pause, Resume, Stop, Private Mode, and Open Omi actions.

Audio is captured as PCM16 mono at 16 kHz. Native Android emits PCM chunks to Flutter, where `PhoneMicSource` splits the stream into 320-byte frames and `LocalWalSyncImpl` stores them locally before upload. If the socket is down or upload is disabled, frames remain queued in WAL for later sync.

Private Mode and local Stop/Pause always win over plugin policy. The app never auto-starts capture after reboot.

## Limitations

Android may silence or deprioritize microphone capture when another app has audio priority. The feature detects this with `AudioRecordingCallback`, audio mode, RMS / dBFS, and zero-frame ratios. It must not report normal recording while receiving all-zero audio.

Call and communication capture is constrained by Android. Advanced Ambient Capture treats calls and meeting apps as awareness/degraded states, not guaranteed call recording.

Recording conversations may require consent depending on jurisdiction and context.
