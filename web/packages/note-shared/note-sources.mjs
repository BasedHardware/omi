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
  return (segments ?? []).flatMap((segment) =>
    segment?.id ? [segment.id] : []
  );
}

/**
 * A structured note with its display text repaired (title, overview, sections), for
 * derived surfaces such as share metadata and preview images that read raw fields.
 */
export function presentableNoteStructured(structured, transcriptIDs = []) {
  if (!structured || typeof structured !== "object") return structured;
  return {
    ...structured,
    title: presentableNoteTitle(structured.title, transcriptIDs),
    overview: presentableNoteText(structured.overview, transcriptIDs),
    sections: Array.isArray(structured.sections)
      ? structured.sections.map((section) =>
          section && typeof section === "object"
            ? presentableNoteSection(section, transcriptIDs)
            : section
        )
      : structured.sections,
  };
}

// Citation-shaped bracket tokens in a title: a transcript segment UUID, the
// compact `s01234` form, or a `^1` footnote marker.
const TITLE_CITATION_TOKEN =
  /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|s[0-9]{4,}|\^[0-9]+)$/i;
const TITLE_SPEAKER = /^(?:spk|speaker)[ _]\p{Nd}+:?$/iu;
const TITLE_OPEN = "[［【";
const TITLE_CLOSE = "]］】";
const SLOT_BASE = 0xf00; // slot digits U+E100..U+EFFF

/** Balanced bracket groups that are not inside another closed group. */
function titleBracketGroups(input) {
  const groups = [];
  let stack = [];
  const flush = () => {
    for (const open of stack) groups.push(...open.inner);
    stack = [];
  };
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (c === "\n") flush();
    else if (TITLE_OPEN.includes(c)) stack.push({ start: i, inner: [] });
    else if (TITLE_CLOSE.includes(c) && stack.length) {
      const open = stack.pop();
      const group = {
        start: open.start,
        end: i + 1,
        nested: open.inner.length > 0,
      };
      if (stack.length) stack[stack.length - 1].inner.push(group);
      else groups.push(group);
    }
  }
  flush();
  return groups.sort((a, b) => a.start - b.start);
}

function isTitleCitation(content, known) {
  const bare = content.replace(/[\u200b\u200c\u200d\u2060\ufeff]/g, "").trim();
  if (TITLE_SPEAKER.test(bare)) return true;
  return bare
    .split(/[\s,;]+/)
    .filter(Boolean)
    .every((token) => known.has(token) || TITLE_CITATION_TOKEN.test(token));
}

function slotDigits(index) {
  let digits = "";
  do {
    digits = String.fromCharCode(0xe100 + (index % SLOT_BASE)) + digits;
    index = Math.floor(index / SLOT_BASE);
  } while (index > 0);
  return digits;
}

/**
 * Read-time repair of a conversation title. Titles keep ordinary bracketed
 * words ("Project [Q3]", "Call [Kickoff]"): only bracket units made of known
 * IDs, citation-shaped IDs or a speaker label are debris, and a nested group
 * ("[Project [s01234]]") is kept whole. Everything else the note repair does
 * (bare known IDs, speaker labels, citation parentheses and links) applies as
 * for any note text.
 */
export function presentableNoteTitle(text, transcriptIDs = []) {
  const input = text ?? "";
  const known = new Set(transcriptIDs.filter(Boolean));
  let mask = "\uE012";
  while (input.includes(mask)) mask += "\uE012";
  const kept = [];
  let masked = "";
  let last = 0;
  for (const group of titleBracketGroups(input)) {
    const unit = input.slice(group.start, group.end);
    if (!group.nested && isTitleCitation(unit.slice(1, -1), known)) continue;
    masked +=
      input.slice(last, group.start) +
      mask +
      slotDigits(kept.length) +
      "\uE013";
    kept.push(unit);
    last = group.end;
  }
  masked += input.slice(last);
  const escaped = mask.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return presentableNoteText(masked, [...known]).replace(
    new RegExp(`${escaped}([\\uE100-\\uEFFF]+)\\uE013`, "g"),
    (slot, digits) => {
      let index = 0;
      for (const digit of digits)
        index = index * SLOT_BASE + digit.charCodeAt(0) - 0xe100;
      return kept[index] ?? slot;
    }
  );
}
