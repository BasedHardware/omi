# Staged artifact read boundary: deterministic read faults end the GPU chain

`batch_worker_failed error_class=ValueError stage=fetch_decode` (x71/30m in
the Loop S sensor) is the staged-artifact sibling of the deterministic
decode faults the WAV and retained-audio layers already type. The artifact
store's read layer — the first thing every GPU worker touches — raised bare
`ValueError` for four faults that are permanent on the pinned bytes: a
staging reference that is not owner/segment-bound, a stored object past its
kind's payload bound, an envelope without the staging magic, and
authenticated decryption that can never succeed (raw cryptography
`InvalidTag`, a rotated key, a tampered body). Every retry re-downloads and
re-decrypts the identical generation and fails identically, so each stuck
unit walked the whole bounded retry ladder — five full fetch passes, five
`batch_worker_failed` records — before quarantining, and the fenced
recovery sweep then re-fetched the same bytes on every pass.

Failure-Class: FC-deterministic-staged-artifact-read-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

## What changed

- `utils/batch_pipeline/artifacts.py` owns `StagedArtifactInvalid(ValueError)`,
  the read-side member of the typed boundary family
  (`StagedAudioInvalid`, `RetainedAudioInvalid`, `DecodedDurationMismatch`).
  The four deterministic raise sites in `_read`/`_reference` carry the type;
  the decrypt wrap chains the raw cryptography fault as its cause. Raise
  sites carry the type and the boundary reads the type — never an exception
  message — so a new deterministic read fault cannot silently drift back
  onto the ladder.
- The GPU worker's fetch_decode boundary
  (`diarizer/batch_pipeline.py`) extends its staged classification to
  `isinstance(exc, (StagedAudioInvalid, StagedArtifactInvalid))` and keeps
  the closed `staged_audio_invalid` reason token. Terminal custody,
  scheduler evidence and the closed vocabulary are unchanged.
- The recovery sweep (`utils/batch_pipeline/quarantine_recovery.py`) catches
  the artifact sibling exactly like its WAV sibling: hold once under
  `refusal_reason='staged_audio_invalid'`, settle `failed_held`, and never
  re-fetch the same bytes on a later pass.

## What deliberately did not change

Transient read faults stay retryable and untyped: an absent or
generation-mismatched object (`NotFound`, provider preconditions), privacy
generation and policy refusals (`PermissionError`, raised before any byte
is read), storage timeouts and outages, and the deploy-configuration bucket
allowlist refusal. The record lane's own plan-payload JSON decoding is not
the GPU fetch_decode boundary and keeps its lane's fault type. The
projection walk's `payload_contract_violation` predicate already
dispositions the typed class through its ValueError family, so owner-chain
poison-head behavior is unchanged; the walk taxonomy registers the class.

## Test surface

`tests/unit/test_staged_artifact_read_boundary_parity.py` pins the raise
sites cell-by-cell (entrypoint x dimension over the admitted-reference
grid, envelope byte mutations, size bounds, key rotation and identity
binding), the fetch_decode disposition across the flag matrix, ladder
economics (typed faults quarantine on attempt one; the unclassified
ValueError contrast still burns pulls to the attempt cap), the recovery
sweep's hold-once semantics, and the projection predicate pins. The suite
fails on parent by construction: the typed class does not exist there, and
the disposition cells assert a terminal evidence shape the parent never
produced.
