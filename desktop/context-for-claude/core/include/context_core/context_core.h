/*
 * context_core — the portable decision rules behind the local data plane.
 *
 * A flat C ABI on purpose. Swift imports this header directly (SwiftPM on macOS, the swift-winrt
 * host package on Windows) and neither side needs C++ interop enabled, a generated shim, or a
 * matching standard library. Nothing here allocates, owns, or frees: every buffer belongs to the
 * caller for the duration of the call.
 *
 * See README.md in this directory for why these particular rules live here and why tokenization
 * deliberately does not.
 */

#ifndef CONTEXT_CORE_CONTEXT_CORE_H
#define CONTEXT_CORE_CONTEXT_CORE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ session boundaries */

/**
 * Five minutes of silence ends a conversation.
 *
 * Short enough that two unrelated conversations an hour apart do not merge into one
 * unreadable transcript; long enough that thinking, typing, or walking to the kitchen in the
 * middle of one conversation does not shatter it into fragments. The asymmetry is deliberate:
 * recall degrades far more from a session that was split (the line that gave an earlier line
 * its meaning is now in a different session) than from two that were joined.
 */
double ctx_session_default_gap_seconds(void);

/**
 * Given the end of the last stored segment and the start of a new one, should a new session open?
 *
 * `has_last_segment == 0` means nothing has been stored yet, which is always a new session — the
 * alternative is a segment with no parent row.
 *
 * A gap that comes out negative means the wall clock moved backwards on us: an NTP correction,
 * a sleep/wake transition, or a segment finishing out of order because two transcribers run
 * concurrently. Comparing that against the threshold would open a spurious session in the
 * middle of a live conversation for a reason the user can never see, so a backwards clock
 * continues the current session instead. Continuing costs one over-long session; splitting
 * costs context that recall can never put back.
 */
int ctx_should_open_new_session(int has_last_segment,
                                double last_segment_ended_at,
                                double next_segment_started_at,
                                double gap_seconds);

/* ---------------------------------------------------------------------- audio */

/**
 * Computes the RMS of signed 16-bit little-endian PCM, normalised to 0...1.
 *
 * A null buffer and a buffer shorter than one sample are silence. An odd final
 * byte is ignored: capture callbacks can be cut across a sample during a
 * device-format change, and losing that byte is preferable to taking down an
 * active conversation. The caller retains ownership of `bytes`.
 */
double ctx_pcm_rms_int16le(const uint8_t *bytes, size_t byte_count);

/**
 * Encodes normalised float samples into the 16-bit little-endian wire format.
 *
 * Values outside -1…1 are clamped rather than allowed to wrap, because a wrapped sample is a
 * full-scale sign flip: an audible click that also drags the RMS of its window over the silence
 * floor and wakes the model for nothing. NaN is treated as silence.
 *
 * Bytes are assembled by hand so the output is little-endian on any host — this data is written
 * to disk and passed between processes, and it must not silently depend on the byte order of the
 * machine that produced it.
 *
 * `out_bytes` must have room for `sample_count * 2` bytes. Returns the number of bytes written
 * (always `sample_count * 2` when `samples` is non-null).
 */
size_t ctx_pcm_encode_int16le(const float *samples, size_t sample_count, uint8_t *out_bytes);

/**
 * Decodes 16-bit little-endian wire format back into normalised float samples.
 *
 * The inverse of `ctx_pcm_encode_int16le` up to one LSB. A trailing odd byte is ignored for the
 * same reason as in `ctx_pcm_rms_int16le`: capture callbacks can be cut across a sample during a
 * device-format change, and losing that byte is preferable to taking down an active conversation.
 *
 * `out_samples` must have room for `byte_count / 2` samples. Returns the number of samples
 * written.
 */
size_t ctx_pcm_decode_int16le(const uint8_t *bytes, size_t byte_count, float *out_samples);

/**
 * Averages interleaved channels down to mono.
 *
 * Averaging rather than taking the first channel: USB interfaces and headsets routinely put the
 * microphone on one channel and silence on the other, and picking a channel would lose that input
 * entirely on half of them. Averaging keeps it at -6 dB, which the transcriber handles and a
 * missing channel is not.
 *
 * `channels <= 1` returns zero samples written (the caller should use the input untouched).
 * A sample count that is not a whole number of frames truncates the partial frame: device format
 * changes produce ragged buffers, and losing one frame is not worth a crash.
 *
 * `out_mono` must have room for `sample_count / channels` samples. Returns the number of mono
 * samples written.
 */
size_t ctx_pcm_downmix_mono(const float *interleaved, size_t sample_count, int channels,
                            float *out_mono);

/* ------------------------------------------------------------------- recall ranking */

/**
 * Blends the two comparable relevance signals with an age penalty.
 *
 *     relevance = 0.6 * coverage + 0.4 * lexical                                        [0, 1]
 *     recency   = exp(-age_seconds / 3 days)                                            (0, 1]
 *     score     = relevance * (0.75 + 0.25 * recency)                                   [0, 1]
 *
 * `coverage` is the fraction of distinct query words the document contains and `lexical` is the
 * document's bm25 quality normalised against the best hit **of its own FTS table** — the caller
 * computes both, because only it knows which table a row came from.
 *
 * Recency is a multiplier capped at the recency pull, not an additive term, so it is bounded by
 * construction: an infinitely old hit still keeps 75% of its relevance. A newer hit can therefore
 * only overturn a relevance gap smaller than 25%.
 *
 * A negative `age_seconds` is clamped to zero rather than rewarded, so a row newer than whatever
 * the caller measured age against cannot score above the ceiling.
 */
double ctx_recall_score(double coverage, double lexical, double age_seconds);

/**
 * Hits scoring below this fraction of the best hit are dropped instead of padding the result to
 * the caller's limit. Relative rather than absolute because scores are only meaningful within one
 * query: there is no absolute number that separates "relevant" from "noise" across every corpus.
 *
 * 0.40 is chosen against the floor of a full-coverage hit. A document containing *every*
 * distinct query term scores at least `0.6 * 1.0 * 0.75 = 0.45`, and no score can exceed 1.0, so
 * the floor can never remove a hit that matched the whole query however old it is. It only ever
 * trims partial-coverage hits.
 */
double ctx_relevance_floor(double best_score);

/* ------------------------------------------------------------------ moment grouping */

/**
 * One screen frame, reduced to exactly what the grouper reads.
 *
 * `key_offset`/`key_length` address a byte range in the caller's `key_bytes` buffer identifying the
 * window — normally the app name and the title reduced to its words. The bytes are compared for
 * equality and nothing else: this library never decodes, cases, or trims them, because doing any of
 * that correctly needs Unicode tables the caller already has.
 *
 * `word_offset`/`word_count` address a run in the caller's `words` buffer. The values are opaque
 * hashes and **must be distinct within a frame** — they stand for a set, and a duplicate would
 * inflate the frame's own word count and depress its measured novelty.
 */
typedef struct ctx_moment_frame {
    double at;
    size_t key_offset;
    size_t key_length;
    size_t word_offset;
    size_t word_count;
} ctx_moment_frame;

/**
 * Groups frames into moments, writing the group each frame belongs to into `out_group_of_frame`.
 *
 * A moment is a run of frames from one window that keeps showing substantially the same thing.
 * `frames` must be in ascending time order. Groups are numbered from zero in the order they opened,
 * every frame is assigned to exactly one, and nothing is dropped — this call gathers, it does not
 * filter.
 *
 * Grouping is per window key rather than strictly adjacent, because a person alternates between two
 * windows every few frames; adjacency would restart both moments on every switch and dedupe almost
 * nothing (measured: 2x versus 5x on a real corpus).
 *
 * A moment ends when the next frame of that window arrives a gap or more later, or when it shows
 * materially new text. "Materially" cannot be a fixed similarity threshold, because the two cases
 * that must come out differently look the same to one: a static page re-OCR'd and a chat window
 * that gained a message both overlap their predecessor by ~95%. What separates them is *novelty* —
 * words the moment has never contained — and how much novelty is normal **for that window**.
 *
 * Returns the number of groups, or -1 when an argument is inconsistent (a null output for a
 * non-empty input, or a frame addressing bytes or words outside the buffers it was given).
 * `out_group_of_frame` must have room for `frame_count` entries.
 */
int32_t ctx_moment_groups(const ctx_moment_frame *frames,
                          size_t frame_count,
                          const char *key_bytes,
                          size_t key_bytes_length,
                          const int64_t *words,
                          size_t words_length,
                          int32_t *out_group_of_frame);

/**
 * Semantic version of the rules above, as a static string the caller must not free.
 *
 * A host that ships a stale copy of this library would answer the same question differently from
 * the one that wrote the database, so the version is reported rather than assumed.
 */
const char *ctx_core_version(void);

#ifdef __cplusplus
}
#endif

#endif /* CONTEXT_CORE_CONTEXT_CORE_H */
