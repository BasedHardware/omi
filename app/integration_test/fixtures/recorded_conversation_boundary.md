# Recorded-conversation replay

`recorded_conversation_boundary.json.gz` is the response fixture for
`integration_test/recorded_conversation_boundary_test.dart`. It retains the
placed-speech timestamps and deduplication result from the November 16 recording
report. Speech, summaries, people, source identifiers and conversation identifiers
are synthetic. It contains no customer audio.

The four windows reflect a 15-minute family/fundraising gap, a later seven-minute
placed-transcript gap and the existing two-hour cap. Missing transcript does not
prove acoustic silence. This fixture uses deterministic adversarial outline
output; it does not measure live model behavior or processing latency.

From the repository root, expose only this fixture on loopback:

```sh
mkdir -p .agent-artifacts/recorded-boundary
gzip -dc app/integration_test/fixtures/recorded_conversation_boundary.json.gz > .agent-artifacts/recorded-boundary/fixture.json
python3 -m http.server 8766 --bind 127.0.0.1 --directory .agent-artifacts/recorded-boundary
```

Run the iPhone simulator integration target with
`--dart-define=RECORDED_BOUNDARY_FIXTURE_URL=http://127.0.0.1:8766/fixture.json`.
Without that define, it is explicitly skipped. The target uses real providers,
HTTP decoding, Home and detail widgets. The HTTP server is hermetic. Transcript
export reaches a mocked native-share boundary; no outbound share is sent.
The repeated checks cover Summary, Transcript, Select, export and return to Home.
The sanitizer deliberately removes audio metadata from this fixture. The original
source rows contain audio metadata; this replay does not qualify its playback.
Audio behavior is covered separately by the existing audio regressions.
