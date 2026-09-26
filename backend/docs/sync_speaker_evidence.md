# Offline speaker evidence, 2026-09-21

## Proven baseline and limits

The supplied `decisions.txt` was parsed with
`python backend/scripts/analyze_speaker_decisions.py /path/to/decisions.txt`.
It contains **10,666 parsable decisions**, zero malformed decisions, spanning
13:12:00.531903Z through 14:02:23.258001Z. No customer identifiers or audio are
included here. The task's 1,448-decision / 22-user summary is reproduced **exactly by retaining
finite runner-up distances**: the multi-candidate cohort, excluding `inf` rows.
It has 195 accepts (13.47%). Its four length buckets contain 526/515/175/232
decisions and 26/56/31/82 accepts respectively; median best distances are
0.8225/0.794/0.743/0.6935. A five-second floor loses 1,041 of these decisions and
82 of the 195 accepts (42.05%). 1,116 of its 1,253 rejections have logged distance
above 0.65; 291 lie in (0.65, 0.75] (295 if both endpoints are included). This cohort is especially relevant to distinguishing taught people
from the owner; it must not be presented as the whole population.

| Service | Decisions | Distinct users | Accepts | Accept rate |
| --- | ---: | ---: | ---: | ---: |
| All | 10,666 | 91 | 1,090 | 10.22% |
| Fresh sync | 1,062 | 18 | 152 | 14.31% |
| Backfill | 9,604 | 87 | 938 | 9.77% |

Users overlap across services. Decisions are repeated observations, not independent
people or necessarily distinct conversations.

| Longest segment | Decisions | Accepts | Median best distance |
| --- | ---: | ---: | ---: |
| 0–2s | 4,079 | 94 | 0.885 |
| 2–5s | 3,632 | 211 | 0.872 |
| 5–10s | 1,340 | 352 | 0.822 |
| 10s+ | 1,615 | 433 | 0.819 |

Of 9,576 rejections, 8,730 have a logged distance greater than 0.65; 1,072
are in the inclusive 0.65–0.75 band. A five-second single-segment floor would
exclude 7,711 recorded decisions, including 305 existing accepts. Rounded log
values cannot settle decisions exactly at a threshold or margin boundary.

The old `clip_seconds` is **segment duration**, while extraction caps at ten
seconds after clamping to WAV bounds. It does not measure embedded duration.
Finite runner-up distance indicates at least two comparable candidate voiceprints;
it does not establish which candidate is correct. The logs have no per-speaker segment counts, total available audio, embeddings,
correct identity, or persisted conversation linkage. They cannot establish how
many speakers would gain evidence, simulate centroid distances, measure recall
or false accepts, or justify retuning. Length associations are confounded by
speaker, recording conditions, diarization, enrollment and service mix.

## Design and alternatives

Union and clamp speaker intervals to real WAV frames. Rank distinct intervals by
length; pack up to 30 seconds without inter-turn silence into at most three
balanced clips, each at most ten seconds. Compare their normalized mean embedding
using the same helper as live. Preserve sync's one-second **total** eligibility
floor and the existing longest-segment speaker priority for person dedup.

Synthetic accounting proves four nonoverlapping two-second turns yield eight
embedded seconds rather than two (4x evidence, still one call). A long speaker
can contribute thirty rather than ten seconds, with up to three rather than one
embedding calls. These are capacity bounds, **not measured production uplift**.
Remaining audio above thirty seconds is excluded to bound cost. Clip failures
retain successful evidence and log failed clip counts. If no embedding succeeds,
the attempt produces an explicit counted terminal reason. Subsecond turns may collectively
reach the same one-second floor. This is a compatibility floor, not an assertion
that one second is reliably identifiable.

Rejected alternatives:

- Five-second eligibility: loses existing coverage; streaming's ability to wait
  does not apply to a completed batch.
- Three longest short clips only: discards a fourth two-second turn and embeds
  each noisy short turn separately. Packing uses more of the available evidence.
- Unlimited concatenation: unbounded provider payload/cost; one long query also
  bypasses live's measured centroid semantics.
- Majority voting or averaging separately accepted labels: substitutes a different
  decision rule. Compare once after pooling embeddings.
- Looser threshold or margin: telemetry has no ground truth. Both remain unchanged.

Concatenation introduces splice boundaries; diarization contamination can mix
voices. Balanced clips reduce tiny-tail weighting, but cannot repair bad speaker
clusters. Their accuracy effect requires real paired evaluation.

## Prediction and falsification

**Inferred prediction:** speakers with multiple clean turns will usually have
lower genuine-match distance and more accepts; single short turns retain
eligibility. The population accept-rate change has unknown size and could be
negative if pooled turns contain another voice. No numeric uplift is claimed.
False accepts may decrease as evidence improves, or increase with contaminated
clusters. The unchanged boundary does not guarantee unchanged precision.

After deployment, rerun the analyzer separately by service, finite-runner-up cohort
and evidence policy;
compare matched cohorts, available seconds, selected clips, failures, and distance
and margin distributions. New insufficient-evidence outcomes expand the decision
denominator, so compare both all attempts and actual comparisons. The first manual
review counter measures corrected / (corrected + confirmed) segments among users
who reviewed automatic labels. It cannot validate unreviewed labels or estimate
population FAR. Logs contain joinable IDs only operationally, never metric labels.

To justify a boundary change, collect a consented, speaker-labelled cross-session
holdout including taught household confusers and unknown speakers. Freeze
train/tuning/test splits by household and session. Replay single-clip and pooled
queries on exactly the same audio with the existing boundary; report coverage,
false rejects, wrong enrolled-person accepts and unknown-speaker accepts with
confidence intervals by duration and service. Choose any new operating point on
tuning data under an agreed false-accept constraint, then assess it once on the
untouched holdout. Human corrections can prioritize cases for review but cannot
supply the unbiased negatives this experiment requires.
