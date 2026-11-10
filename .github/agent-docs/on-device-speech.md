# On-device speech transcription

- `app/ios/Runner/SpeechDeadline.swift` owns deadlines for SpeechAnalyzer availability and recognition. A timeout may leave a shared model download running, but must finish recognition cleanup before replying to Dart. Native speech results and timeout callbacks use the main queue for one-shot completion.
- `PurePollingSocket` keeps one provider operation in flight. Do not wrap it in `Future.timeout`: that cannot cancel native/HTTP work and permits duplicate transcription. Providers own timeouts and throw failures so retained audio can be retried; an empty successful result means no speech.
- Native deadline regression: `ruby app/ios/test/speech_deadline_test.rb` (local/CI manifest). Dart regressions (from `app/`): `flutter test test/unit/pure_polling_test.dart test/unit/on_device_transcription_upgrade_test.dart`.

## Mobile freemium engine rollback

The existing iOS speech channel selects SpeechAnalyzer/SpeechTranscriber on supported iOS 26 hardware and locales, reserving and installing its OS-managed asset through AssetInventory. Unsupported hardware/locales, model-install or recognition failures fall back to the existing on-device SFSpeech path. Existing fallback UX/status strings are retained; there is no Parakeet setup in this path.

`mobile-speech-analyzer-disabled` is an inverted PostHog operational kill switch, registered in `config/feature-flags.yaml`. Missing/false/error/offline keeps the improved engine selected; true forces SFSpeech for both availability probing and transcription. It is read per operation through the existing identity/consent-fenced analytics adapter. Users with analytics disabled retain the shipped new-engine default. The flag does not affect cloud STT, overflow, summaries, schedules or plans.

Android's existing Whisper provider splits canonical PCM WAV input into at most 30-second independent plugin calls. The pinned plugin creates/frees a whisper_context for each call; failure propagates so polling retains the complete input for retry.

## Runtime readiness loss (issue #20484)

Readiness is a point-in-time check. If an SFSpeech request subsequently fails,
`SpeechFallbackCoordinator` probes the real legacy recognizer again. An unavailable
probe becomes `LocalSpeechUnavailable`; a healthy probe preserves the original
failure for ordinary retry. Classification does not parse localized messages or
assume every recognition failure means missing assets. The internal completion is
a typed result, so NSError domain/code survive to the channel and the existing
bounded custom STT log. Timeouts remain failures; successful silence stays empty.

The existing Dart provider maps setup failures to `LocalSttFailure`. Polling keeps
the failed frames, leaves the raw-audio connection running, and retries recognition
only after a successful readiness probe (periodically or via the existing Retry
action). Its memory buffer remains bounded; durable capture/WAL is the authority
for longer outages and restarts. Only the disposable recognition WAV is removed.
No setting, original recording, account data, or firmware is reset, and no paid or
cloud transcription is selected on the user's behalf. The default-off overflow
path already performs a readiness check after its own platform errors.

Verification and rollout checklist:

- [x] Native behavioral regression: readiness lost after a successful probe,
  analyzer fallback and rollback, original diagnostic preservation, healthy
  transient failure, and successful silence.
- [x] Dart provider/polling regression: actionable error, no repeated recognition
  while unavailable, exact retained audio retried after recovery, temporary WAV
  cleanup, and saved recording left intact.
- [ ] Merge and release an iOS build containing this change; no backend deployment
  is required for this app-only fix.
- [ ] Physical iPhone: missing/unavailable assets and permission/Dictation changes
  during capture, recovery in the same session, background/foreground, and saved
  audio after restart. Check both supported SpeechAnalyzer and legacy paths.
- [ ] Physical CV1: compare phone-mic capture with pendant capture, then test each
  affected transcription mode, voice chat, and capture after silence/reconnect.
  Match failures to app/iOS/firmware versions and a private recording timestamp.
- [ ] Clarify the photo source/accessory and reproduce its transfer failure before
  attributing it to the CV1 firmware or claiming an app-side fix.

Firmware AAD/microphone wake behavior remains separate (PR #14156 needs hardware
qualification and release). A phone-side recognizer fix cannot restore audio that
was never sampled or delivered. Keep issue #20484 open pending those checks; its
reported cloud, voice and photo failures are not proven to share this cause.
