# Device storage recovery

LIFECYCLE: permanent

Gets the audio a wearable recorded on its own off the device and into the offline
log, where the existing sync engine uploads it as a conversation. Ports the
Flutter storage syncs (`app/lib/services/wals/ring_storage_sync.dart` and
`storage_sync.dart`, the protocol authority).

## The gap this closes

A wearable keeps recording when your laptop is asleep, closed, or across the
room. That audio sits in the device's own storage until something reads it out.
Windows had no reader, so on Windows the device was only ever a microphone that
happened to be wireless: everything it captured while unattended stayed on it
until the ring wrapped around and overwrote it.

The offline log (`main/wal/`) already knows how to upload a recording the live
socket never got. This package is the other half: the part that gets those
recordings off the device in the first place.

## Three firmware generations, one service

All three protocols live on service `30295780`. Commands and bulk data share
`30295781`; status is read from `30295782`.

| Generation | Shape | Read out by |
|---|---|---|
| Ring buffer (fw 3.0.20+) | one sequence of fixed 444 byte records, with a device-side read pointer | `ringDrain.ts` |
| Multi-file (LittleFS) | a numbered listing; read and delete address files by position | `fileDrain.ts` |
| Legacy SD card | the same file commands with a smaller reply | `storageProtocol.ts` |

`storageDrainService.ts` picks between them: read the ring status first, and only
fall through to the file listing if the device does not answer it. A ring that
answers with nothing unread means the device is empty, not that it might speak
the older protocol, so the file listing is not probed. Sending file commands to a
ring device can abort a transfer that is already in flight.

## The two invariants

**A recording is only released once its audio is durably stored.** For the ring
that means the read pointer is advanced last, after every chunk is persisted; for
files it means a file is deleted only after its own audio is stored. Anything
that fails leaves the device holding the audio, so the next pass re-reads it.
That costs duplicated work and never costs audio. Every failure path in both
drains exists to preserve this ordering, and the mutation audit in the PR seeds
regressions against each one.

**Files are deleted highest index first.** The firmware addresses files by their
position in the listing and re-indexes what remains downward after a delete, so
deleting index 0 first shifts 1 and 2 down and the next delete removes the wrong
recording. `deletionOrder()` is the whole of that rule.

## Capture time

A recovered recording is identified by its capture source plus its start second,
and that identity is what the offline log dedupes on. So the timeline has to
advance.

Both drains anchor on the first payload and place later audio relative to that
anchor by the duration already read, which is what Flutter does with
`chunkTimerStart`. Two cases would otherwise collapse to a single timestamp and
throw away everything after the first chunk:

- A device whose clock is not valid (`rtcValid` false in the ring status). The
  anchor becomes the drain time minus the estimated duration of the unread
  region, so the audio is dated behind now instead of at it.
- A stored file large enough to split into several chunks whose payloads all
  carry one timestamp.

The estimate uses the codec's nominal encoded frame length, so it is a placement
hint and never a value anything decides on.

## Files

| File | Holds |
|---|---|
| `storageProtocol.ts` | command encoders, notification and listing parsers, payload unpacking, the frame boundary rule, `deletionOrder` |
| `storageChunker.ts` | groups drained frames into the bounded chunks that become uploads, and stamps each frame |
| `ringDrain.ts` | the ring transfer and the read-pointer ordering |
| `fileDrain.ts` | the listing, per-file transfer, and delete ordering |
| `storageDrainService.ts` | protocol selection, the read-only probe, cancellation, and the sink that writes into the offline log |

## Who drives it

`deviceController.ts` builds one service per session. On connect it probes only,
which reads the status characteristic and nothing else, and reports what the
device is holding. The transfer itself runs only when the user asks for it from
the Device tab. This matches Flutter, where `setisDeviceStorageSupport` probes on
connect and `syncAll` is a button. A full device can take minutes to drain and
shares the radio with the live session, so starting it unprompted would degrade
recording for people who never asked to recover anything.
