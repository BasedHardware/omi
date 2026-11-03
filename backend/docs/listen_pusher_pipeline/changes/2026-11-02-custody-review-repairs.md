# Framed custody review repairs

Framed replay proof now performs a fresh, bounded raw-live listing, even when
archive READ is disabled. It compares generation-pinned decoded custody PCM as
well as projections, fails closed on listing/proof errors, and excludes only the
receipt currently being projected. A conflicting extended projection cannot hide
earlier custody. Raw playback also gives earlier media creation times precedence
over later overlapping raw receipts, independent of listing/window order.
Native-rate raw captures are compared in the requested replay rendition, so a
matching 16 kHz replay of a 44.1 kHz capture is verified rather than rejected.
The native captured bytes remain unchanged.

Frame rendition offsets and lengths use cumulative whole-stream resampler
boundaries. Original capture offsets/counts remain available to readers at other
output rates. Contiguity uses original capture endpoints, so rendition rounding
cannot create a false gap or overlap between adjacent frames. Captured bytes,
frame starts, gaps and samples are unchanged. Frame
validation shares pusher's existing 1 ms overlap tolerance; accepted jitter no
longer prevents a receipt. Replay proof caches and charges whole objects by
bucket/path/generation, then selects each span independently.

The [custody contract](../../listen_pusher_pipeline.mdx) and receipt-before-phone-
release rule are unchanged. AUDIO_CUSTODY_FRAMED_PERCENT remains default 0,
STOP_PCM remains off, and no deployment, ramp or slice-4 reader is included.
Hermetic regression evidence is recorded in the ic-custody repair handoff.
