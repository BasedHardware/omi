import { repairNoteCitations } from "./note-citations.mjs";

/** Only typed provenance resolving to this loaded transcript can become a source chip. */
export function resolvableNoteSources(sourceIDs = [], transcriptIDs = []) {
  const valid = new Set(transcriptIDs.filter(Boolean));
  return [...new Set(sourceIDs)].filter((id) => valid.has(id));
}

/**
 * Read-time repair of one summary section. Inline citations the repair removes
 * join the section's typed provenance, so a legacy note whose only evidence was
 * an inline `[s01234]` keeps its transcript chip (macOS `presentableSection`).
 */
export function presentableNoteSection(section, transcriptIDs = []) {
  const stored = section.source_segment_ids ?? [];
  const known = [...transcriptIDs.filter(Boolean), ...stored];
  const heading = repairNoteCitations(section.heading ?? "", known);
  const body = repairNoteCitations(section.body_markdown ?? "", known);
  return {
    ...section,
    heading: heading.text,
    body_markdown: body.text,
    source_segment_ids: resolvableNoteSources(
      [...stored, ...heading.sourceIDs, ...body.sourceIDs],
      transcriptIDs
    ),
  };
}

/**
 * Read-time repair of a single-line note field (title, action item, event).
 * Generation already sweeps these; this covers notes stored before it did.
 */
export function presentableNoteText(text, transcriptIDs = []) {
  return repairNoteCitations(text ?? "", transcriptIDs.filter(Boolean)).text;
}

/** Transcript segment IDs a loaded conversation can resolve sources against. */
export function noteTranscriptIDs(segments = []) {
  return (segments ?? []).flatMap((segment) => (segment?.id ? [segment.id] : []));
}
