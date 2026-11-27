# Live words: provider first, cut at an End, the End's tail in the summary; no name before the end

Two per-account flags in the family of `2026-11-25-reliability-rollouts-per-account.md`. Each changes
nothing for an account its rule does not admit.

## `live_words_cascade` (needs `vendor_recognizer_on_opened_app`; its End parts need `end_open_conversation`)

The display stream (`/v4/live-words`) stays display only. Three things change around it.

**Order of the live words.** The app's merged list showed the phone's own recogniser first and the
provider's words only in its holes. Now, per stretch of audio time, it shows the provider's words where
it has them and the phone's own only where it has none; stored text still replaces both. The phone's
recogniser is not started for an account whose language is multi-language or outside its list. A live
word stays on screen until a stored line covers its moment of audio or, where stored text exists to
compare with, until it is five minutes old; that holds for a conversation that has ended as well.

**An End cuts the display line.** The phone sends `{"type":"end"}` as a text message on the display
connection, between the audio frames captured before and after the End. The server remembers that
point of the audio and starts a new line there (`LineJoiner.cut`), so no display line holds words from
both sides of a user End. Any other text message, and every text message for an account without the
flag, is ignored as before.

**The End's tail reaches the first summary.** `POST /v1/conversations` accepts `live_tail`: the words
the phone was showing for the conversation being ended, with their times on the phone's capture clock.
It is hidden from the published schema and accepted raw, so a malformed one cannot fail an End.

- `utils/conversations/v3/live_tail.py` checks and bounds it on arrival: at most 600 words, 6,000
  characters and 200 lines, plain text (control characters and bracket characters removed), only words
  that start before the End and at most six hours before it.
- It is stored encrypted with the owner's key on the End's own document
  (`users/{uid}/conversation_v3_manual_cuts`), and nowhere else. It is never written to a conversation,
  a recording row or a transcript.
- When the conversation that End closed is summarised, the words no stored line covers (2 s reach) and
  that lie inside the conversation follow the transcript in the notes prompt, marked as a draft. That
  prompt is the only reader, so what the notes say (title, summary, the action items they propose) can
  reflect those words; the discard and wake-word checks, memory extraction and search read the stored
  transcript alone.
- The number of tail words the notes read, and when the first of them was spoken, are stamped on the
  conversation before the notes are written (`v3_summary_tail_words`, `v3_summary_tail_since`). Stored
  words that land afterwards in that stretch are taken to be that speech, up to that number, so the
  late-speech rewrite rule counts only what goes beyond it; speech from before the stretch that lands
  late counts in full. The grouping pass marks such a landing
  (`v3_tail_absorbed`), and a summary pass that was still running settles instead of failing with
  `processing_source_changed` and writing the notes again. A landing with words the notes have not read
  drops the mark and the settle fails as before.
- The stored words are removed when a later summary pass finds them all covered, when the credit is
  used up, or at the owner's next End with a tail, which clears the tails of Ends between one and eight
  days old. There is no timed sweep: a tail whose speech never lands and whose owner sends no End with
  a tail in that week stays (encrypted, at most 6,000 characters).

This is a deliberate, bounded exception to the rule that client-authored text is display only (the
rule `tests/unit/test_client_processing_trust_boundary.py` proves for `client_processing`, which this
change does not touch): for an admitted account, phone-authored words reach one model prompt, and
through it the conversation's notes.

Queries added on `conversation_v3_manual_cuts`: one equality read on `at` per summary pass of a
conversation an End closed, and one range read on `at` (at most 50 rows) per End that carries a tail.

`POST /v1/conversations` treats a body that holds only `live_conversation_id` and `live_tail` as the
app's Finish body, as it treats one with `live_conversation_id` alone, so an End with a tail takes the
same path as one without. A backend without this change does not: admit an account only once the
service that answers `/v1/conversations` runs it (the flag tool's live check enforces this).

Not covered: the display stream still needs a load-balancer path rule before a wide ramp.

## `title_at_end`

An open conversation that holds three minutes of speech gets a one-off title from a small model call
(`CONVERSATIONS_V3_LIVE_TITLE`). For an admitted account `_maybe_publish_live_title` returns before
claiming an attempt: no model call, no title written, and the outline names the conversation when it
ends. A title already published on an open row is left as it is. The app reads "Listening" for any
conversation in progress under the same flag.
