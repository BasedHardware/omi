# Gapped, unframed raw-live packs

A live capture pack can carry a nonzero `gap_count` without a declared
`frame_schema`. `CapturePack.append` increments `gap_count` whenever the next
frame's server-projected timestamp differs from the previous frame's end by more
than 2 ms, and again for every retained zero-sample frame. `capture_start` and
`capture_end` span the whole wall interval, while the omi-wal payload is only
the concatenation of captured packets. `LiveAudioArchive._write` sets
`frame_schema` only when `AUDIO_CUSTODY_FRAMED_PERCENT` admits the owner and
every frame has samples, so the default fleet writes gapped packs with no frame
table in the media metadata.

`raw_audio_read.list_packs` previously skipped every such pack, and
`_decode_pack` measured its expected length from the wall span, so a gapped pack
could neither be listed nor decoded. The writer does keep the exact frame
positions: `audio_outbox.commit_capture` always writes the custody manifest
beside the media under the same name, even when the media metadata omits
`custody_manifest_path`. This change reads that manifest for gapped, unframed
packs and positions each recorded frame on the capture clock.

- Listing emits one entry per contiguous run, with `raw_offset_samples` into the
  unchanged pack and the frame's true `start`. Gaps stay explicit; nothing is
  closed or resampled across them.
- Decoding walks the recorded frames (`decode_capture_frames`), verifies each
  packet against the manifest's byte range and digest, and skips retained
  zero-sample frames. The expected length is the sum of recorded samples, not
  the wall span.
- `retained_record_units` now honors `raw_offset_samples` and the fragment span.
  Without that, a multi-entry pack was read whole for every entry, duplicating
  audio and closing the writer's gaps. `sealed_received_audio_seconds` therefore
  counts only captured samples; `sealed_received_stt_seconds` still spans the
  gap because that silence is what a batch provider is billed for.
- A missing, ambiguous, or mismatched manifest keeps the pack excluded. No
  audio is fabricated, no timestamp is shifted, and no retained bytes are
  deleted.

`RAW_LIVE_GAPPED_PACKS_ENABLED` is a default-on ops kill switch through
`config/refactor_modes.py`. Setting it to `off` restores the previous skip in
both listing and decoding. The switch does not change the writer, the manifest
format, or the framed path.
