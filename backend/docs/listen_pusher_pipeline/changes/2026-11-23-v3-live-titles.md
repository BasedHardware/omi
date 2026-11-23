# Live titles for v3 conversations

The v3 builder can name an open conversation after three minutes of accumulated
transcribed speech. The preview uses one managed GPT-6 Luna attempt with
at most 1,024 input tokens and 32 output tokens. The gateway rate card bounds
the estimated cost at $0.00012160 per eligible conversation. The existing
Home and detail refreshes read the title from the same conversation.
See the [pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).

## Production readback

Verify that the serving gateway has the live-title lane before enabling a
builder revision with live titles. A missing lane during rollout can consume
the conversation's single attempt.

- On David's TestFlight build, record a continuous conversation with a
  recognizable topic. Leave it running beyond five minutes of transcribed
  speech. Record when Home and detail first show the title, and confirm
  the same row is still `in_progress` in production. Record the serving
  revisions and UTC read time. Keep conversation text out of shared evidence.
- At a fixed UTC cut, use a production conversation snapshot with one row
  per owner and conversation ID. Take current rows with `v3_derived=true`,
  `status=in_progress`, `tile_state=live`, and no delete or discard marker.
  Report titled and total counts for rows started over five minutes before
  the cut. Repeat for rows with at least 300 seconds of nonempty, decoded
  transcript intervals using `deduplicated_transcribed_speech_seconds`.
  A titled row has a nonblank `structured.title`. Report unreadable speech
  rows separately.
- For the same production UTC days, count unique owner-day pairs with v3
  conversation activity. Sum gateway estimated cost for
  `lane_id="omi:auto:conversation-v3-live-title"` and `payer="omi"` across
  all accounted attempts, including failed attempts with reported usage.
  Divide micro-USD by one million and by the owner-day count. Use the
  gateway attempt ledger or `llm_gateway_estimated_cost_micro_usd_total`
  and report missing or indeterminate cost coverage from
  `llm_gateway_accounted_attempts_total` separately. Reconcile billed
  failures against provider billing where available.
