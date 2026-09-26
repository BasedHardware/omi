# On-device speech transcription

- `app/ios/Runner/SpeechDeadline.swift` owns deadlines for SpeechAnalyzer availability and recognition. A timeout may leave a shared model download running, but must finish recognition cleanup before replying to Dart. Native speech results and timeout callbacks use the main queue for one-shot completion.
- `PurePollingSocket` keeps one provider operation in flight. Do not wrap it in `Future.timeout`: that cannot cancel native/HTTP work and permits duplicate transcription. Providers own timeouts and throw failures so retained audio can be retried; an empty successful result means no speech.
- Native deadline regression: `ruby app/ios/test/speech_deadline_test.rb` (local/CI manifest). Dart regressions (from `app/`): `flutter test test/unit/pure_polling_test.dart test/unit/on_device_transcription_upgrade_test.dart`.
