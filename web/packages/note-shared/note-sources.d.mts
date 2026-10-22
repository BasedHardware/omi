export function resolvableNoteSources(sourceIDs?: readonly string[], transcriptIDs?: readonly string[]): string[];
export interface PresentableNoteSectionInput {
  heading?: string | null;
  body_markdown?: string | null;
  source_segment_ids?: readonly string[] | null;
}
export function presentableNoteSection<T extends PresentableNoteSectionInput>(
  section: T,
  transcriptIDs?: readonly string[]
): T & { heading: string; body_markdown: string; source_segment_ids: string[] };
export function presentableNoteText(text: string | null | undefined, transcriptIDs?: readonly string[]): string;
export function noteTranscriptIDs(segments?: readonly ({ id?: string | null } | null | undefined)[] | null): string[];
export function presentableNoteStructured<T>(structured: T, transcriptIDs?: readonly string[]): T;
export function presentableNoteTitle(text: string | null | undefined, transcriptIDs?: readonly string[]): string;
