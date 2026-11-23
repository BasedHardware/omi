# Phone WAL receipt verification

Record-lane audio can reach durable storage before a transcript exists. Capable phone builds
request the [Listen audio receipt](../../listen_pusher_pipeline.mdx#durable-audio-outbox-default-on)
and compare its mapped frames with their local safety copy. A transcript receipt can carry
frames from a matching committed manifest. The client release switch defaults off during
shadow qualification. The normal app train and a verified audit precede cohort expansion.

The server and app share the `app/test/fixtures/listen_audio_custody.json` wire example.
`test_audio_durable_outbox.py` verifies it against the committed media and manifest.
