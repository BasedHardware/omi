# Queued transcription and expired empty placeholders

The owner saw queued recordings in Needs attention as Couldn't transcribe.
Try Again called summary processing on a capture with no transcript. First
seal could arrive more than a day after the display wait had started.

The [Home transcription contract](../../listen_pusher_pipeline.mdx#home-transcription-presentation)
now uses immutable first seal admission as a bounded presentation anchor,
guards pending reprocess before any summary claim/model, and presents expired
zero-content in-progress placeholders as read-only noise. All three behaviors
have independent default-on kill switches documented there. No GPU, provider,
lease capacity, audio proof, or backlog-release policy changes.

Native seal and proof repair already wrote record_admitted_at once; no-job seal
registration now preserves that same fact. Existing stamped queued rows need
no write. Legacy retained-audio retry jobs missing all seal clocks require the
separate bounded operator queue observation; its script defaults to dry-run and
has not been applied by this implementation lane. Reads never query jobs or
write documents. The explicit operator tool reads a bounded owner scope and
CAS-rechecks its sampled jobs; it writes only one observation field per eligible
row, never resets it, and never changes pending generations or jobs.

Build 1563 (source b78ea0112d82) and main have the same relevant reprocess
decoder/provider contract: HTTP 200 processing with nonfailed home_step clears
the failed ID and moves the row into processing. The separate 409 code maps to
the existing error toast. Empty placeholder wires are completed/noise with a
nonempty terminal caption, preventing old empty-title transcription inference.
This is backend source/HTTP replay evidence, not a physical-app rendering or
production recovery claim.

Focused regressions cover read-only projections, exactly bounded clocks,
title-independent pending evidence, no model calls, both client wire shapes,
late content/curation/producer release, and one-shot strict Firestore CAS.
