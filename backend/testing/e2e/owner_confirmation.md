# Native owner excerpt acceptance

This fixture exercises the production speaker prompt routes, selection, evidence
binding, clip delivery and strict Firestore assignment transaction. Storage,
identity, model output and authentication are synthetic. The Flutter target uses
the production card, provider, just_audio and transcript widget. It is not a
voice-recognition benchmark, an authenticated product session or a physical-device
acceptance receipt.

On macOS, make six seconds of synthetic speech:

```sh
say -o /tmp/owner-confirm-speech.aiff 'We should ship it on Friday.'
ffmpeg -y -i /tmp/owner-confirm-speech.aiff -af apad -t 6 -ar 16000 -ac 1 -f s16le /tmp/owner-confirm-speech.pcm
```

Start the fixture from `backend/`, using the offline encryption secret supplied
by `backend/test.sh` (no cloud credentials):

```sh
OMI_ENV_STAGE=offline ENCRYPTION_SECRET=<offline-test-secret> .venv/bin/python -m testing.e2e.owner_confirmation_fixture --pcm /tmp/owner-confirm-speech.pcm
```

Use a separate dev bundle on an emulator. Android's emulator host alias reaches
the loopback-only server. A running iOS simulator can use the default 127.0.0.1,
but its native audio output must be functional.

```sh
cd app
flutter run --debug --flavor dev -d <emulator-id> --dart-define=OWNER_CONFIRMATION_FIXTURE_URL=http://10.0.2.2:18955 -t integration_test/owner_confirmation_capture.dart
```

Connect `agent-flutter` using that run's log and snapshot before each interaction.
Use stable keys (`speaker_tag_prompt_play`, `speaker_tag_prompt_answer_me`,
`speaker_tag_prompt_answer_not_me`, `speaker_tag_prompt_answer_skip`) rather than
assuming filtered snapshot reference numbers identify a control.

1. Reset unknown excerpt. Yes/No are disabled until all six seconds finish.
2. Play, then Yes. The played row becomes You. Its same-speaker sibling remains
   Speaker 1; the independent automatic owner remains You.
3. Reset owner excerpt. Play, then No. Only the played row becomes Speaker 1.
   Its same-speaker sibling and independent automatic owner remain You.
4. Reset unknown excerpt and Skip without playback. Labels stay unchanged.
5. Refresh after each answer. There is no second owner question for that fixture
   conversation until the explicit test-only reset deletes the durable quota.

The label change commits after the production Undo window. Inspect
`GET /fixture/receipt` and `GET /fixture/transcript` on loopback: only the played
segment has a segment-only receipt, no whole-speaker receipt or voice-learning
grant is created, and the synthetic enrolled-owner embedding is unchanged.

The field-scoped marker consumes quota on issuance. Reset is a test-only fixture
endpoint and is never mounted by a production entrypoint.
