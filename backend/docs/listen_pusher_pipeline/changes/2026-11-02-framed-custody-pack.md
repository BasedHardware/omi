# Framed custody windows (dark)

`AUDIO_CUSTODY_FRAMED_PERCENT` defaults to zero independently of archive
COALESCE. Admitted v2 pusher sessions retain the existing 60 s / 16 MiB bound,
4096 frames, conversation changes and shutdown boundaries, but a send pause
does not flush the window. Captured bytes remain unchanged; each frame pins
its start, samples, gap marker and digest in the immutable manifest. Raw and
projection discovery expose separate frame spans with decoded sample offsets.
Media without a manifest is invisible to the new discovery path. Readers
continue understanding existing framed objects after rollback to percent zero.

Receipts still require both generations and both plaintext SHA-256s. ACKs
remain per committed part; an uncommitted tail does not release the phone WAL.
No STOP_PCM change, lifecycle change, deploy, or ramp is included.

The lead trains this only after batch holds 100 through Monday peak: matched
hour after the carrying GKE roll, 5% for at least 12 h, then 100%. Refuse any
step with missing raw-read counter, rising window_tail would-drop or custody
failures, playback or batch STT errors, or a staged WAL release without a
receipt. Restart comparison if batch percent or playback-on-demand changes.
Infracost tracks measured writes/object creation per step and settled billing
the next day. Until applied, savings are zero. The $17–21/day Coldline and
$10–13/day writes are estimates; Coldline starts about 30 days after writer ramp.
