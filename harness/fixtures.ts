/** Synthetic-only fixture: never loaded from an external corpus. */
export const placementConversation = {
  owner_account_id: "owner-david",
  capture_session_id: "synthetic-session-1",
  stream_id: "synthetic-chat",
  utterances: [
    { source_unit_ref: "turn-1", speaker_ref: "speaker:alice", mention_ref: "mention:alice", text: "Alice Rivera prefers concise status updates.", event_time: "2026-07-29T10:00:00Z" },
    { source_unit_ref: "turn-2", speaker_ref: "speaker:bob", mention_ref: "mention:he", text: "He also asked for an audit trail.", event_time: "2026-07-29T10:01:00Z" },
    { source_unit_ref: "turn-3", speaker_ref: "speaker:unknown", mention_ref: "mention:bare-he", text: "He may disagree.", event_time: "2026-07-29T10:02:00Z" },
  ],
} as const;
