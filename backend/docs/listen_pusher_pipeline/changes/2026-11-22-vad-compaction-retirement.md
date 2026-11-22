# Retire final-pass VAD compaction

`TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED` served off on every surface
since its 2026-10-15 creation, so the code removal fixes every read to that
value: stored-audio shadow ASR calls the shadow transcribe directly on each
audio window, and the shared pyannote final-pass seam diarizes the complete
original PCM unit. Word, turn, overlap and embedding clocks stay on the
original timeline; original audio is never replaced upstream, in-flight work
is unchanged, and the record lane's whole-unit pyannote path is untouched.

The removal deletes the default-off wrapper (`utils/stt/vad_compaction.py`),
its env read (`config/final_pass_vad.py`), and the dedicated compaction unit
tests. The batch pipeline's own internal diarization compaction
(`speech_compaction.diarized_seconds` provenance) is a separate mechanism and
is unchanged. No client wire format changes, no Nemotron routing.

See [the pipeline contract](../../listen_pusher_pipeline.mdx) and
[the generated flag registry](../../feature-flag-registry.md).
