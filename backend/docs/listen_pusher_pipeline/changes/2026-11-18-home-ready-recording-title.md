# Neutral title for a ready recording without notes

The legacy conversation list could mark a completed batch row ready because
its transcript had landed, then blank its stored placeholder title on the
wire. The result was a blank tile even though the recording could be opened.

When a ready row has a batch projection receipt and only a generated
placeholder headline, the list now displays the neutral label `Recording`.
Existing Home state and visibility decisions still apply. The label uses no
transcript text or time-zone lookup and makes no storage changes.

Canary with the legacy list projection and verify that a receipt-bearing
placeholder-only row gets the label without a preview. Rows still waiting
on transcription, locked rows, and rows with user titles or notes preserve
their existing presentation. Revert this commit to roll back.
