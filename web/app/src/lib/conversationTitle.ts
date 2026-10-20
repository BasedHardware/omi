import {
  noteTranscriptIDs,
  presentableNoteText,
} from '@omi/note-shared/note-sources.mjs';

interface TitledConversation {
  structured?: { title?: string | null } | null;
  transcript_segments?: readonly ({ id?: string | null } | null | undefined)[] | null;
}

/**
 * The title as displayed: citation debris (`[s01234]`, `Speaker_00`) repaired against the
 * conversation's transcript, as for note sections. Display only — edit and save paths keep
 * `structured.title`. Empty when the stored title is empty or only debris.
 */
export function conversationDisplayTitle(conversation: TitledConversation): string {
  return presentableNoteText(
    conversation.structured?.title,
    noteTranscriptIDs(conversation.transcript_segments),
  );
}
