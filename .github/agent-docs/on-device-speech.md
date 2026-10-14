# On-device speech transcription

- `app/ios/Runner/SpeechDeadline.swift` owns deadlines for SpeechAnalyzer availability and recognition. A timeout may leave a shared model download running, but must finish recognition cleanup before replying to Dart. Native speech results and timeout callbacks use the main queue for one-shot completion.
- `PurePollingSocket` keeps one provider operation in flight. Do not wrap it in `Future.timeout`: that cannot cancel native/HTTP work and permits duplicate transcription. Providers own timeouts and throw failures so retained audio can be retried; an empty successful result means no speech.
- Native deadline regression: `ruby app/ios/test/speech_deadline_test.rb` (local/CI manifest). Dart regressions (from `app/`): `flutter test test/unit/pure_polling_test.dart test/unit/on_device_transcription_upgrade_test.dart`.

## Mobile freemium engine rollback

The existing iOS speech channel selects SpeechAnalyzer/SpeechTranscriber on supported iOS 26 hardware and locales, reserving and installing its OS-managed asset through AssetInventory. Unsupported hardware/locales, model-install or recognition failures fall back to the existing on-device SFSpeech path. Existing fallback UX/status strings are retained; there is no Parakeet setup in this path.

`mobile-speech-analyzer-disabled` is an inverted PostHog operational kill switch, registered in `config/feature-flags.yaml`. Missing/false/error/offline keeps the improved engine selected; true forces SFSpeech for both availability probing and transcription. It is read per operation through the existing identity/consent-fenced analytics adapter. Users with analytics disabled retain the shipped new-engine default. The flag does not affect cloud STT, overflow, summaries, schedules or plans.

Android's existing Whisper provider splits canonical PCM WAV input into at most 30-second independent plugin calls. The pinned plugin creates/frees a whisper_context for each call; failure propagates so polling retains the complete input for retry.
