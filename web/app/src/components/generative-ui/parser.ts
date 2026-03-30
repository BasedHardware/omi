/**
 * XML tag parser for generative UI components.
 * Splits content into segments of markdown and custom UI tags,
 * matching the Flutter app's XmlTagParser.
 */

// ============================================================================
// Types
// ============================================================================

export type SegmentType =
  | 'markdown'
  | 'quote-board'
  | 'followups'
  | 'pie-chart'
  | 'accordion'
  | 'timeline'
  | 'highlight'
  | 'table'
  | 'rich-list'
  | 'task'
  | 'flow'
  | 'study';

export interface ContentSegment {
  type: SegmentType;
  raw: string;
}

export interface MarkdownSegment extends ContentSegment {
  type: 'markdown';
  content: string;
}

// Quote Board
export interface QuoteData {
  speaker: string;
  time?: string;
  record?: 'on the record' | 'background' | 'off the record' | string;
  text: string;
}

export interface QuoteBoardSegment extends ContentSegment {
  type: 'quote-board';
  quotes: QuoteData[];
}

// Followups
export interface FollowupItem {
  type?: 'question' | 'fact-check' | 'verification' | string;
  text: string;
}

export interface FollowupsSegment extends ContentSegment {
  type: 'followups';
  items: FollowupItem[];
}

// Pie Chart
export interface ChartSegmentData {
  label: string;
  value: number;
  color?: string;
}

export interface PieChartSegment extends ContentSegment {
  type: 'pie-chart';
  title?: string;
  chartType: 'pie' | 'donut' | 'bar';
  segments: ChartSegmentData[];
}

// Accordion
export interface AccordionSection {
  title: string;
  content: string;
}

export interface AccordionSegment extends ContentSegment {
  type: 'accordion';
  title?: string;
  allowMultiple: boolean;
  sections: AccordionSection[];
}

// Timeline
export interface TimelineEvent {
  time?: string;
  label?: string;
  text: string;
}

export interface TimelineSegment extends ContentSegment {
  type: 'timeline';
  title?: string;
  events: TimelineEvent[];
}

// Highlight
export interface HighlightSegment extends ContentSegment {
  type: 'highlight';
  color: string;
  text: string;
}

// Table
export interface TableSegment extends ContentSegment {
  type: 'table';
  title?: string;
  rows: string[][];
}

// Rich List
export interface RichListItem {
  title: string;
  description?: string;
  thumb?: string;
  url?: string;
}

export interface RichListSegment extends ContentSegment {
  type: 'rich-list';
  items: RichListItem[];
}

// Task
export interface TaskStep {
  title: string;
}

export interface TaskRef {
  time?: string;
  by?: string;
  text: string;
}

export interface TaskSegment extends ContentSegment {
  type: 'task';
  title: string;
  priority?: 'high' | 'medium' | 'low';
  summary?: string;
  steps: TaskStep[];
  refs: TaskRef[];
}

// Flow
export interface FlowStep {
  type: 'main' | 'exception';
  text: string;
}

export interface FlowSegment extends ContentSegment {
  type: 'flow';
  title: string;
  steps: FlowStep[];
}

// Study
export interface StudyQuestion {
  question: string;
  answer: string;
  options: string[];
}

export interface StudySegment extends ContentSegment {
  type: 'study';
  title?: string;
  questions: StudyQuestion[];
}

export type ParsedSegment =
  | MarkdownSegment
  | QuoteBoardSegment
  | FollowupsSegment
  | PieChartSegment
  | AccordionSegment
  | TimelineSegment
  | HighlightSegment
  | TableSegment
  | RichListSegment
  | TaskSegment
  | FlowSegment
  | StudySegment;

// ============================================================================
// Helpers
// ============================================================================

function parseAttributes(attrString: string): Record<string, string> {
  const attrs: Record<string, string> = {};
  const pattern = /(\w[\w-]*)\s*=\s*"([^"]*)"/g;
  let m;
  while ((m = pattern.exec(attrString)) !== null) {
    attrs[m[1]] = m[2];
  }
  return attrs;
}

// ============================================================================
// Tag Patterns
// ============================================================================

interface TagParser {
  pattern: RegExp;
  parse: (match: RegExpExecArray) => ParsedSegment | null;
}

const quoteboardParser: TagParser = {
  pattern: /<quote-board>([\s\S]*?)<\/quote-board>/g,
  parse: (match) => {
    const inner = match[1];
    const quotePattern = /<quote\s+([^>]*)>([\s\S]*?)<\/quote>/g;
    const quotes: QuoteData[] = [];
    let qm;
    while ((qm = quotePattern.exec(inner)) !== null) {
      const attrs = parseAttributes(qm[1]);
      quotes.push({
        speaker: attrs.speaker || 'Unknown',
        time: attrs.time,
        record: attrs.record,
        text: qm[2].replace(/^[""]|[""]$/g, '').trim(),
      });
    }
    if (quotes.length === 0) return null;
    return { type: 'quote-board', raw: match[0], quotes };
  },
};

const followupsParser: TagParser = {
  pattern: /<followups>([\s\S]*?)<\/followups>/g,
  parse: (match) => {
    const inner = match[1];
    const itemPattern = /<item\s*([^>]*)>([\s\S]*?)<\/item>/g;
    const items: FollowupItem[] = [];
    let im;
    while ((im = itemPattern.exec(inner)) !== null) {
      const attrs = parseAttributes(im[1]);
      items.push({ type: attrs.type, text: im[2].trim() });
    }
    if (items.length === 0) return null;
    return { type: 'followups', raw: match[0], items };
  },
};

const chartParser: TagParser = {
  pattern: /<pie-chart\s*([^>]*)>([\s\S]*?)<\/pie-chart>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const segPattern = /<segment\s+([^/]*?)\/>/g;
    const segments: ChartSegmentData[] = [];
    let sm;
    while ((sm = segPattern.exec(inner)) !== null) {
      const sa = parseAttributes(sm[1]);
      if (sa.label && sa.value) {
        segments.push({
          label: sa.label,
          value: parseFloat(sa.value),
          color: sa.color,
        });
      }
    }
    if (segments.length === 0) return null;
    return {
      type: 'pie-chart',
      raw: match[0],
      title: attrs.title,
      chartType: (attrs.type as 'pie' | 'donut' | 'bar') || 'bar',
      segments,
    };
  },
};

const accordionParser: TagParser = {
  pattern: /<accordion\s*([^>]*)>([\s\S]*?)<\/accordion>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const sectionPattern = /<section\s+([^>]*)>([\s\S]*?)<\/section>/g;
    const sections: AccordionSection[] = [];
    let sm;
    while ((sm = sectionPattern.exec(inner)) !== null) {
      const sa = parseAttributes(sm[1]);
      sections.push({ title: sa.title || 'Section', content: sm[2].trim() });
    }
    if (sections.length === 0) return null;
    return {
      type: 'accordion',
      raw: match[0],
      title: attrs.title,
      allowMultiple: attrs['allow-multiple'] === 'true',
      sections,
    };
  },
};

const timelineParser: TagParser = {
  pattern: /<timeline\s*([^>]*)>([\s\S]*?)<\/timeline>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const eventPattern = /<event\s+([^>]*)>([\s\S]*?)<\/event>/g;
    const events: TimelineEvent[] = [];
    let em;
    while ((em = eventPattern.exec(inner)) !== null) {
      const ea = parseAttributes(em[1]);
      events.push({ time: ea.time, label: ea.label, text: em[2].trim() });
    }
    if (events.length === 0) return null;
    return { type: 'timeline', raw: match[0], title: attrs.title, events };
  },
};

const highlightParser: TagParser = {
  pattern: /<highlight\s*([^>]*)>([\s\S]*?)<\/highlight>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    return {
      type: 'highlight',
      raw: match[0],
      color: attrs.color || 'yellow',
      text: match[2].trim(),
    };
  },
};

const tableParser: TagParser = {
  pattern: /<table\s*([^>]*)>([\s\S]*?)<\/table>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const rowPattern = /<row>([\s\S]*?)<\/row>/g;
    const cellPattern = /<cell>([\s\S]*?)<\/cell>/g;
    const rows: string[][] = [];
    let rm;
    while ((rm = rowPattern.exec(inner)) !== null) {
      const cells: string[] = [];
      let cm;
      while ((cm = cellPattern.exec(rm[1])) !== null) {
        cells.push(cm[1].trim());
      }
      if (cells.length > 0) rows.push(cells);
    }
    if (rows.length === 0) return null;
    return { type: 'table', raw: match[0], title: attrs.title, rows };
  },
};

const richListParser: TagParser = {
  pattern: /<rich-list>([\s\S]*?)<\/rich-list>/g,
  parse: (match) => {
    const inner = match[1];
    const itemPattern = /<item\s+([^/]*?)\/>/g;
    const items: RichListItem[] = [];
    let im;
    while ((im = itemPattern.exec(inner)) !== null) {
      const attrs = parseAttributes(im[1]);
      if (attrs.title) {
        items.push({
          title: attrs.title,
          description: attrs.description,
          thumb: attrs.thumb,
          url: attrs.url,
        });
      }
    }
    if (items.length === 0) return null;
    return { type: 'rich-list', raw: match[0], items };
  },
};

const taskParser: TagParser = {
  pattern: /<task\s+([^>]*)>([\s\S]*?)<\/task>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const summaryMatch = /<summary>([\s\S]*?)<\/summary>/.exec(inner);
    const stepPattern = /<step\s*([^/>]*)(?:\/>|>([\s\S]*?)<\/step>)/g;
    const refPattern = /<ref\s+([^>]*)>([\s\S]*?)<\/ref>/g;
    const steps: TaskStep[] = [];
    const refs: TaskRef[] = [];
    let sm;
    while ((sm = stepPattern.exec(inner)) !== null) {
      const sa = parseAttributes(sm[1]);
      steps.push({ title: sa.title || sm[2]?.trim() || '' });
    }
    let rm;
    while ((rm = refPattern.exec(inner)) !== null) {
      const ra = parseAttributes(rm[1]);
      refs.push({ time: ra.t, by: ra.by, text: rm[2].trim() });
    }
    return {
      type: 'task',
      raw: match[0],
      title: attrs.title || 'Task',
      priority: attrs.priority as 'high' | 'medium' | 'low' | undefined,
      summary: summaryMatch?.[1]?.trim(),
      steps,
      refs,
    };
  },
};

const flowParser: TagParser = {
  pattern: /<flow\s+([^>]*)>([\s\S]*?)<\/flow>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const stepPattern = /<step\s*([^>]*)>([\s\S]*?)<\/step>/g;
    const steps: FlowStep[] = [];
    let sm;
    while ((sm = stepPattern.exec(inner)) !== null) {
      const sa = parseAttributes(sm[1]);
      steps.push({
        type: (sa.type as 'main' | 'exception') || 'main',
        text: sm[2].trim(),
      });
    }
    return { type: 'flow', raw: match[0], title: attrs.title || 'Flow', steps };
  },
};

const studyParser: TagParser = {
  pattern: /<study\s*([^>]*)>([\s\S]*?)<\/study>/g,
  parse: (match) => {
    const attrs = parseAttributes(match[1]);
    const inner = match[2];
    const qPattern = /<q>([\s\S]*?)<\/q>/g;
    const questions: StudyQuestion[] = [];
    let qm;
    while ((qm = qPattern.exec(inner)) !== null) {
      const qInner = qm[1];
      const answerMatch = /<a>([\s\S]*?)<\/a>/.exec(qInner);
      const optPattern = /<o>([\s\S]*?)<\/o>/g;
      const options: string[] = [];
      let om;
      while ((om = optPattern.exec(qInner)) !== null) {
        options.push(om[1].trim());
      }
      const questionText = qInner
        .replace(/<a>[\s\S]*?<\/a>/, '')
        .replace(/<o>[\s\S]*?<\/o>/g, '')
        .trim();
      questions.push({
        question: questionText,
        answer: answerMatch?.[1]?.trim() || '',
        options,
      });
    }
    if (questions.length === 0) return null;
    return { type: 'study', raw: match[0], title: attrs.title, questions };
  },
};

// ============================================================================
// Main Parser
// ============================================================================

const ALL_PARSERS: TagParser[] = [
  quoteboardParser,
  followupsParser,
  chartParser,
  accordionParser,
  timelineParser,
  highlightParser,
  tableParser,
  richListParser,
  taskParser,
  flowParser,
  studyParser,
];

interface TagMatch {
  start: number;
  end: number;
  segment: ParsedSegment;
}

export function parseGenerativeContent(content: string): ParsedSegment[] {
  const matches: TagMatch[] = [];

  for (const parser of ALL_PARSERS) {
    // Reset lastIndex for global regex
    parser.pattern.lastIndex = 0;
    let m;
    while ((m = parser.pattern.exec(content)) !== null) {
      const segment = parser.parse(m);
      if (segment) {
        matches.push({ start: m.index, end: m.index + m[0].length, segment });
      }
    }
  }

  if (matches.length === 0) {
    return [{ type: 'markdown', raw: content, content }];
  }

  // Sort by position
  matches.sort((a, b) => a.start - b.start);

  // Remove overlapping matches (keep first)
  const filtered: TagMatch[] = [];
  let lastEnd = 0;
  for (const m of matches) {
    if (m.start >= lastEnd) {
      filtered.push(m);
      lastEnd = m.end;
    }
  }

  // Build segments interleaving markdown and components
  const segments: ParsedSegment[] = [];
  let cursor = 0;

  for (const m of filtered) {
    if (m.start > cursor) {
      const md = content.slice(cursor, m.start).trim();
      if (md) segments.push({ type: 'markdown', raw: md, content: md });
    }
    segments.push(m.segment);
    cursor = m.end;
  }

  if (cursor < content.length) {
    const md = content.slice(cursor).trim();
    if (md) segments.push({ type: 'markdown', raw: md, content: md });
  }

  return segments;
}

export function containsGenerativeTags(content: string): boolean {
  return ALL_PARSERS.some((p) => {
    p.pattern.lastIndex = 0;
    return p.pattern.test(content);
  });
}
