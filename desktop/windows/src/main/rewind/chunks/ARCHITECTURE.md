# Rewind video chunks

LIFECYCLE: permanent

Packs runs of Rewind's per-frame JPEGs into inter-frame-compressed video chunks.
Ported from macOS `Rewind/Core/VideoChunkEncoder.swift`,
`RewindVideoFrameCursor.swift` and `RewindAbandonedVideoChunkRecovery.swift`.

## The problem, measured

Windows Rewind stores one JPEG per captured frame (`frameFile.ts`,
`<userData>/rewind/<day>/<ts>.jpg`). Capture runs at one frame per second
(`captureService.ts`, `intervalMs: 1000`) with a duplicate-frame skip and a
30-second keyframe anchor, and retention defaults to 14 days
(`rewindSettings.ts`).

Measured on this machine's own capture output at the default `standard` quality
tier (1280x720, JPEG quality 0.7), a real 60-second run of ordinary desktop work:

| Storage | Per frame | Per 60s chunk |
|---|---|---|
| JPEG (what ships today) | 115.8 KB | 6.95 MB |
| H.264 chunk @ 400 kbps | **2.26 KB** | **136 KB** |
| VP9 chunk @ 400 kbps | 3.35 KB | 201 KB |

**51x**, with every one of the 60 frames decoding back and scoring 37 to 41 dB
PSNR against its source. The saving is that large because consecutive frames of a
screen are nearly identical, which is exactly the redundancy a JPEG-per-frame
store cannot exploit and an inter-frame codec exists to.

Scaled to the shipped defaults that is the difference between roughly 25 GB and
roughly 0.5 GB for a fortnight of active use. macOS never had this problem
because it has encoded to 60-second chunks from the start.

## Shape

```
compactionPlan  ->  compactor  ->  chunkFormat  ->  chunkFiles
                        |
                        +-- chunkBroker --> renderer/rewind/chunkEncoder (WebCodecs)
```

| Module | Answers |
|---|---|
| `compactionPlan.ts` | Which frames become which chunk? |
| `chunkSql.ts` | Which frames may be compacted, and how is one claimed? |
| `compactor.ts` | In what order, so that nothing can be lost? |
| `chunkFormat.ts` | What is in the file? |
| `chunkFiles.ts` | Where does it live, and when is it garbage? |
| `cursorPolicy.ts` | Can the open decoder serve this read? |
| `chunkBroker.ts` | How does main get an encode done? |
| `chunkRebuild.ts` | What rows should exist for a chunk after a database wipe? |
| `compactionRunner.ts` | When does any of this happen? |

Reading a compacted frame runs the other way, and does not come through the
broker: `renderer/rewind/frameImageSource.ts` asks main for the chunk's bytes
and decodes locally with `chunkDecoder.ts`.

## Compaction, not live encoding

This is the deliberate divergence, and the rest of the design follows from it.

macOS encodes **live**: `VideoChunkEncoder.addFrame` takes each frame as it is
captured and appends it to the chunk currently being written. Windows compacts
**after the fact**: capture keeps writing JPEGs exactly as it always has, and a
background pass every 30 minutes packs runs that are older than 30 minutes.

The reason is that live encoding puts the codec in the capture path. A bug there
costs the user frames that no longer exist anywhere. Compacting instead means:

- capture is untouched, so compaction cannot lose a frame that was captured;
- a failed compaction leaves the JPEGs exactly where they were;
- turning it off changes nothing about how frames are stored going forward;
- the backlog already on disk gets compacted too, which a live encoder cannot do.

It also removes most of the machinery macOS needs. Because macOS encodes live,
its database rows necessarily exist while the chunk is still being written, so it
carries a sidecar journal of abandoned writers, a quarantine table, and a
generation/reservation ownership model to stop a stale finaliser from clearing a
newer writer's state. Here nothing references a chunk until it is finished, so
none of that is load-bearing. What is kept is the tombstone table, because a
chunk can still be found corrupt at *read* time long after it was written.

## The ordering that makes it safe

```
write chunk  ->  read it back and verify  ->  claim frame  ->  delete its JPEG
```

Every prefix is a safe place to crash:

| Crash after | State | Who cleans up |
|---|---|---|
| write | an unreferenced chunk file | the chunk sweep, after its grace period |
| verify | same | same |
| a claim | claimed frames read from a chunk proven to hold them; unclaimed frames still have their JPEGs | nothing to clean; the chunk holds a superset |
| a claim, before the delete | an orphaned JPEG | the existing orphan sweep |

"Verify" re-reads the file from disk and checks that it parses, holds exactly the
planned number of frames, carries the planned capture timestamp at every offset,
and has the planned geometry. The timestamp check is the one that matters: a
chunk with the right frame count but a shifted order would make every read return
a neighbouring frame, silently.

## Rules worth knowing

**Only OCR'd frames are compacted.** `chunkSql.ts` requires `indexed = 1`. The
OCR backlog sweep reads `image_path` for `indexed = 0` frames and, when the file
is missing, marks the frame indexed with *empty text* rather than failing
(`ocrService.ts`). Compacting an un-OCR'd frame would therefore not error; it
would quietly cost that frame its searchable text forever.

**A chunk holds one geometry and one local day.** A video track has exactly one
size, and chunks are filed under a day directory so day-scoped retention can
delete whole files.

**Runs shorter than 8 frames are left alone.** The opening key frame is most of a
short chunk: measured, a 5-frame run only reached 2.4x against the 51x of a
60-frame run. Below the floor it is not worth replacing a directly-readable JPEG
with a decode.

**Presentation timestamps come from the frame index, not the capture clock.**
macOS derives them from a live capture rate, and documents what that cost: a
mid-chunk rate change (plugging in power shrinks the capture interval 3x) made a
later frame's timestamp fall below an already-appended one, which `AVAssetWriter`
rejects as non-monotonic, dropping frames and sometimes discarding the chunk. An
index is monotonic by construction. The real capture time travels per record in
the container instead.

**The read cursor is one-way.** A chunk has no random access, so reaching frame
*n* means decoding everything before it, and reopening per request makes a scrub
quadratic. macOS measured 728 ms to walk an 18-frame chunk reopening each time
against 59 ms keeping the reader alive — 12.3x, pixel-identical. The decision of
when the open decoder can be reused is `cursorPolicy.ts`, a pure state machine;
`chunkDecoder.ts` executes it.

## The container

A custom `.omichunk` rather than MP4. AVFoundation is a muxer-first API, so macOS
gets a container whether it wants one or not; WebCodecs is codec-first, emitting
bare `EncodedVideoChunk`s and accepting them back. An MP4 here would mean writing
a muxer and a demuxer to put bytes into a box structure and immediately take them
out again.

Two properties are worth the format:

- **Frame N is record N.** MP4 seeks by presentation time; here the index is the
  addressing scheme, and it is the same number stored in `chunk_offset`.
- **A chunk is self-describing.** Each record carries the capture timestamp its
  JPEG filename used to carry, so `rebuildIndex.ts` — which re-creates
  `rewind_frames` rows from `<day>/<ts>.jpg` after a database wipe — does not
  lose that ability for every frame compaction touched.

Parsing is defensive: every declared length is checked against the remaining
buffer before use, and a truncated file raises rather than returning the frames it
managed to read, because the compactor treats "reads back exactly" as the
precondition for deleting anything.

## Recovery after a database wipe

`rebuildIndex.ts` exists because Windows can re-create `rewind_frames` rows from
the JPEGs still on disk after a whole-database reset: the filename *is* the
timestamp. Compaction would have quietly taken that away from every frame it
packed, leaving intact pixels that nothing references and that the chunk sweep
would eventually delete.

So the rebuild has a chunk pass too (`chunkRebuild.ts`). It reads only each
chunk's record headers, skips offsets that already have a row so a re-run
inserts nothing, and refuses to invent rows for a chunk that does not parse.

One difference from the JPEG pass is worth knowing: rebuilt chunk rows are
marked `indexed = 1`, not `0`. The OCR backfill reads `image_path`, which is
empty for a chunk-backed row, and its missing-file handling marks the frame
indexed with empty text anyway — so both values reach the same end state and the
only difference is whether the app first spends a run of OCR batches that cannot
succeed. The OCR text itself is genuinely lost, because it lived only in the
wiped database; it was never written into a chunk. The pixels come back.

## Where a frame's pixels are

`rewind_frames` gains `chunk_path` and `chunk_offset` (migration 3). Exactly one
of them and `image_path` locates a frame:

| `image_path` | `chunk_path` | Meaning |
|---|---|---|
| a path | NULL | still its own JPEG (every pre-existing row) |
| `''` | a path | compacted; pixels are frame `chunk_offset` of that chunk |

`image_path` is set to `''` rather than NULL because the column is `NOT NULL` and
readers compare it as a string. macOS carries the identical compromise and says
so.

## Not ported

- **Live encoding**, and with it the aspect-ratio debounce, the frame-rate
  freeze, the buffer-overflow emergency reset, and the writer-not-ready retry
  ladder. All of those exist to keep a live encoder healthy in the capture path.
- **The reservation/generation ownership model** and the abandoned-writer sidecar
  journal, for the reason given above: nothing references a chunk until it is
  complete.
- **`maxResolution` downscaling.** macOS caps a chunk's long edge at 3000 px.
  Windows already caps the captured frame by quality tier
  (`RewindCaptureHost.tsx`, max 2560x1440), so the cap would never bind.
