# Intake envelope typed boundary

The intake envelope (`utils/batch_pipeline/audio.py`) is the shared
reader/writer pair for the authenticated capture-context envelope: 
`with_context` freezes provenance inside a staged WAV and `read_context`
parses it back out. Every batch worker unit, projection manifest and
coverage projection reads its identity through this pair.

## Contract

Every fault the envelope raises is deterministic on the pinned stored
bytes: the same body re-parses and re-authenticates identically on every
attempt, so a retry can never succeed. The batch decode family's doctrine
is that such faults carry the family type `StagedAudioInvalid` (a
`ValueError` subclass) — the same way `decode_pcm16_wav`, `capture_decode`
and the retained-audio decoder wrap sites do. `read_context` was the last
reader in the family whose raise sites stayed anonymous.

Downstream boundaries read the type, never the message:

- every envelope refusal raises `StagedAudioInvalid`;
- the worker's `StagedAudio` decode keeps its fail-open context handling
  unchanged (`except Exception` → context `None`): identity degrades, the
  audio still decodes, and a container-broken body still fails typed at
  `decode_pcm16_wav`;
- the projection path's payload-contract catch (`PAYLOAD_CONTRACT_ERRORS`)
  keeps catching these faults — the type is a `ValueError` subclass — and
  `payload_contract_violation` classifies them as permanent;
- Firestore commit contention surfaces as exactly `type(e) is ValueError`
  with an `Aborted` cause; a typed envelope fault is never `type(e) is
  ValueError`, so the discriminator cannot misread one as the other.

Because the type is a `ValueError` subclass, every existing
`except ValueError` caller keeps catching these faults unchanged. The
observable change is at the typed boundaries: worker fetch_decode evidence,
the terminal worker-validation disposition, and the projection payload
contract now name the fault family instead of collapsing the cohort into
anonymous `ValueError` tokens that production books as unclassified errors
(the bare-`ValueError` envelope-fault cohort behind the
`error_class=ValueError stage=fetch_decode` sensor signature).

## Verdicts

| Fault | Type | Message |
| --- | --- | --- |
| Non-RIFF body, non-WAVE id, or declared size ≠ len − 8 | `StagedAudioInvalid` | `invalid intake WAV envelope` |
| Chunk whose declared size overruns the body | `StagedAudioInvalid` | `truncated intake WAV chunk` |
| Second `OMIM` chunk, or one larger than 64 KiB | `StagedAudioInvalid` | `duplicate or oversized intake context` |
| Missing/unparseable/non-object context, wrong or missing version, trailing bytes | `StagedAudioInvalid` | `authenticated intake context is required` |
| NaN/Infinity in the sealed context, non-RIFF WAV, or body over 64 KiB on write | `StagedAudioInvalid` | `invalid bounded intake context or WAV` |

The chunk walk skips unknown chunks whole (with their pad byte), so a valid
context still reads from bodies that carry extra chunks; the sealed JSON is
canonical (sorted keys, compact separators, `version` stamped by
`with_context`).

The parity grids (`test_intake_envelope_*_grid.py` and
`test_intake_context_typed_boundary.py`) pin the full verdict surface one
cell at a time: header gate, chunk-walk grammar, payload JSON parse,
write-side limit boundary, and the `StagedAudio` fail-open contract.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
