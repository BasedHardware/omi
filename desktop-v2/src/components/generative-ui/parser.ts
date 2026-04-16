import type { ContentSegment, StoryBriefingData } from "./types";
import { richListPattern, parseRichList } from "./parsers/richList";
import { chartPattern, parseChart } from "./parsers/chart";
import { accordionPattern, parseAccordion } from "./parsers/accordion";
import { timelinePattern, parseTimeline } from "./parsers/timeline";
import { quoteBoardPattern, parseQuoteBoard } from "./parsers/quoteBoard";
import { followupsPattern, parseFollowups } from "./parsers/followups";
import { highlightPattern, parseHighlight } from "./parsers/highlight";
import { tablePattern, parseTable } from "./parsers/table";

type ParseFn = (m: RegExpExecArray) => ContentSegment | null;

interface BaseParser {
  pattern: RegExp;
  parse: ParseFn;
}

const baseParsers: BaseParser[] = [
  { pattern: richListPattern, parse: parseRichList },
  { pattern: chartPattern, parse: parseChart },
  { pattern: accordionPattern, parse: parseAccordion },
  { pattern: tablePattern, parse: parseTable },
  { pattern: highlightPattern, parse: parseHighlight },
];

interface RawMatch {
  start: number;
  end: number;
  segment: ContentSegment;
}

function collectMatches(content: string, p: BaseParser): RawMatch[] {
  const out: RawMatch[] = [];
  const re = new RegExp(p.pattern.source, p.pattern.flags);
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) {
    const seg = p.parse(m);
    const full = m[0];
    if (seg) {
      out.push({ start: m.index, end: m.index + full.length, segment: seg });
    } else {
      // Fallback: keep the raw tag as markdown so the page doesn't break.
      out.push({
        start: m.index,
        end: m.index + full.length,
        segment: { kind: "markdown", content: full },
      });
    }
  }
  return out;
}

// Regex from xml_parser.dart:199. Finds a standalone "Timeline" / "## Quotes" /
// "Follow-ups:" header immediately preceding a journalist tag so the header is
// absorbed into the briefing block instead of left behind as lonely text.
const sectionHeaderPattern =
  /(?:^|\n)\s*(#{1,3}\s*)?(Timeline|Quotes?|Quote\s*Board|Follow[\s-]?ups?|Key\s*Tension\s*Points?|Additional\s*Context)[:\s]*$/gim;

function findStartWithHeader(content: string, tagStart: number): number {
  const before = content.substring(0, tagStart);
  sectionHeaderPattern.lastIndex = 0;
  let last: RegExpExecArray | null = null;
  let m: RegExpExecArray | null;
  while ((m = sectionHeaderPattern.exec(before)) !== null) last = m;
  if (last) {
    const headerEnd = last.index + last[0].length;
    const between = content.substring(headerEnd, tagStart);
    if (between.trim() === "") {
      return last.index === 0 ? 0 : last.index;
    }
  }
  return tagStart;
}

function collectJournalistRange(
  content: string,
): { start: number; end: number; data: StoryBriefingData } | null {
  const ranges: [number, number][] = [];
  let data: StoryBriefingData = {};

  const tRe = new RegExp(timelinePattern.source, timelinePattern.flags);
  let tm: RegExpExecArray | null;
  while ((tm = tRe.exec(content)) !== null) {
    const start = findStartWithHeader(content, tm.index);
    ranges.push([start, tm.index + tm[0].length]);
    if (!data.timeline) {
      const parsed = parseTimeline(tm);
      if (parsed) data = { ...data, timeline: parsed };
    }
  }

  const qRe = new RegExp(quoteBoardPattern.source, quoteBoardPattern.flags);
  let qm: RegExpExecArray | null;
  while ((qm = qRe.exec(content)) !== null) {
    const start = findStartWithHeader(content, qm.index);
    ranges.push([start, qm.index + qm[0].length]);
    if (!data.quoteBoard) {
      const parsed = parseQuoteBoard(qm);
      if (parsed) data = { ...data, quoteBoard: parsed };
    }
  }

  const fRe = new RegExp(followupsPattern.source, followupsPattern.flags);
  let fm: RegExpExecArray | null;
  while ((fm = fRe.exec(content)) !== null) {
    const start = findStartWithHeader(content, fm.index);
    ranges.push([start, fm.index + fm[0].length]);
    if (!data.followups) {
      const parsed = parseFollowups(fm);
      if (parsed) data = { ...data, followups: parsed };
    }
  }

  if (ranges.length === 0) return null;
  const start = ranges.reduce((a, r) => Math.min(a, r[0]), Number.POSITIVE_INFINITY);
  const end = ranges.reduce((a, r) => Math.max(a, r[1]), 0);
  return { start, end, data };
}

export function containsGenerativeTags(content: string): boolean {
  return (
    /<rich-list\s*>/i.test(content) ||
    /<pie-chart[\s>]/i.test(content) ||
    /<accordion[\s>]/i.test(content) ||
    /<table(?:-data)?[\s>]/i.test(content) ||
    /<highlight[\s>]/i.test(content) ||
    /<timeline[\s>]/i.test(content) ||
    /<quote-board\s*>/i.test(content) ||
    /<followups\s*>/i.test(content)
  );
}

export function parseGenerativeContent(content: string): ContentSegment[] {
  if (!containsGenerativeTags(content)) {
    return [{ kind: "markdown", content }];
  }

  const matches: RawMatch[] = [];
  for (const p of baseParsers) {
    matches.push(...collectMatches(content, p));
  }

  const journalist = collectJournalistRange(content);
  matches.sort((a, b) => a.start - b.start);

  const segments: ContentSegment[] = [];
  let cursor = 0;
  let briefingAdded = false;

  const pushMarkdown = (from: number, to: number) => {
    if (to <= from) return;
    const chunk = content.substring(from, to).trim();
    if (chunk) segments.push({ kind: "markdown", content: chunk });
  };

  for (const m of matches) {
    if (!briefingAdded && journalist && m.start > journalist.start) {
      pushMarkdown(cursor, journalist.start);
      segments.push({ kind: "storyBriefing", data: journalist.data });
      briefingAdded = true;
      cursor = journalist.end;
    }

    if (journalist && m.start >= journalist.start && m.end <= journalist.end) {
      // Inside the aggregated journalist range — skip; briefing renders it.
      continue;
    }

    pushMarkdown(cursor, m.start);
    segments.push(m.segment);
    cursor = m.end;
  }

  if (!briefingAdded && journalist) {
    pushMarkdown(cursor, journalist.start);
    segments.push({ kind: "storyBriefing", data: journalist.data });
    cursor = journalist.end;
  }

  pushMarkdown(cursor, content.length);
  return segments;
}
