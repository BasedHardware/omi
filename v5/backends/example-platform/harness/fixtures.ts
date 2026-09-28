/** Synthetic-only fixture: never loaded from an external corpus. */
export const placementConversation = {
  owner_account_id: "owner-david",
  capture_session_id: "synthetic-session-1",
  stream_id: "synthetic-chat",
  // This fixture really is synthetic, so it says so explicitly. The label is now
  // the caller's assertion about its own corpus, not a constant in the ingester.
  source_trust: "synthetic",
  event_kind: "synthetic.chat/utterance",
  payload_schema_ref: "synthetic.chat/utterance",
  utterances: [
    { source_unit_ref: "turn-1", speaker_rendering: "speaker:alice", mention_ref: "mention:alice", text: "Alice Rivera prefers concise status updates.", event_time: "2026-07-29T10:00:00Z" },
    { source_unit_ref: "turn-2", speaker_rendering: "speaker:bob", mention_ref: "mention:he", text: "He also asked for an audit trail.", event_time: "2026-07-29T10:01:00Z" },
    { source_unit_ref: "turn-3", speaker_rendering: "speaker:unknown", mention_ref: "mention:bare-he", text: "He may disagree.", event_time: "2026-07-29T10:02:00Z" },
  ],
} as const;
