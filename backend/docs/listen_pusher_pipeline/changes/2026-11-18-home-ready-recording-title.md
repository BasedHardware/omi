# Neutral title for a ready recording without notes

An unlocked ready row with a batch projection receipt displays `Recording`
when its stored fallback headline is the only display content. The legacy
conversation list opts into the label after computing the current Home step.
Detail and other readers keep their title contract even when storage carries a
prepared Home step. With `HOME_STEP_PROJECTION=off` the lists stop adding the
label.

The prepared feed preserves user headlines and notes that live in sections,
action items, or events. Normal writes and preparation include a notes-pending
bit inside the encrypted display. Existing displays with unknown notes status
keep the stored headline for ready receipt-bearing rows. The GET still uses
one document read and does not read transcripts or notes bodies.

Verify both lists with a receipt-bearing generated placeholder, with and without
notes. Revert this change to roll back.
