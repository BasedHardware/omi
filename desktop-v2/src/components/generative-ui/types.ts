// Data shapes for parsed generative-UI tags. Mirrors the Flutter models in
// app/lib/widgets/generative_ui/models/.

export interface RichListItem {
  title: string;
  description?: string;
  thumbnailUrl?: string;
  url?: string;
}

export type ChartKind = "bar" | "pie" | "donut";

export interface ChartSegment {
  label: string;
  value: number;
  color: string; // hex #RRGGBB
}

export interface ChartData {
  title?: string;
  kind: ChartKind;
  segments: ChartSegment[];
}

export interface AccordionItem {
  title: string;
  content: string; // raw markdown, may contain nested generative tags
}

export interface AccordionData {
  title?: string;
  items: AccordionItem[];
  allowMultiple: boolean;
}

export type TimelineLabel =
  | "context"
  | "conflict"
  | "claim"
  | "decision"
  | "reaction"
  | "humanImpact"
  | "nextSteps"
  | "other";

export interface TimelineEvent {
  time: string;
  label: string; // raw label text
  labelType: TimelineLabel;
  description: string;
}

export interface TimelineData {
  title?: string;
  events: TimelineEvent[];
}

export type QuoteRecordStatus =
  | "onTheRecord"
  | "background"
  | "offTheRecord"
  | "unclear";

export interface Quote {
  speaker: string;
  time: string;
  recordStatus: QuoteRecordStatus;
  quote: string;
}

export interface QuoteBoardData {
  quotes: Quote[];
}

export type FollowupType =
  | "factCheck"
  | "verification"
  | "question"
  | "other";

export interface FollowupItem {
  type: FollowupType;
  content: string;
}

export interface FollowupsData {
  items: FollowupItem[];
}

export interface StoryBriefingData {
  timeline?: TimelineData;
  quoteBoard?: QuoteBoardData;
  followups?: FollowupsData;
}

export interface HighlightData {
  text: string;
  color: string; // hex #RRGGBB
}

export interface TableCell {
  content: string;
}

export interface TableRow {
  cells: TableCell[];
}

export interface TableData {
  title?: string;
  rows: TableRow[];
}

export type ContentSegment =
  | { kind: "markdown"; content: string }
  | { kind: "richList"; items: RichListItem[] }
  | { kind: "chart"; data: ChartData }
  | { kind: "accordion"; data: AccordionData }
  | { kind: "highlight"; data: HighlightData }
  | { kind: "table"; data: TableData }
  | { kind: "storyBriefing"; data: StoryBriefingData };

export const CHART_PALETTE = [
  "#8B5CF6",
  "#10B981",
  "#F59E0B",
  "#3B82F6",
  "#EF4444",
  "#A78BFA",
  "#06B6D4",
  "#F97316",
] as const;

export const NAMED_COLORS: Record<string, string> = {
  yellow: "#F9D71C",
  orange: "#F97316",
  green: "#22C55E",
  blue: "#3B82F6",
  purple: "#8B5CF6",
  red: "#EF4444",
  pink: "#EC4899",
  cyan: "#06B6D4",
  amber: "#F59E0B",
  lime: "#84CC16",
  teal: "#14B8A6",
  indigo: "#6366F1",
  white: "#FFFFFF",
  black: "#000000",
  gray: "#6B7280",
  grey: "#6B7280",
};

export function parseColor(input: string | undefined, fallback: string): string {
  if (!input) return fallback;
  const normalized = input.trim().toLowerCase();
  if (NAMED_COLORS[normalized]) return NAMED_COLORS[normalized];
  const hex = normalized.replace(/^#/, "");
  if (/^[0-9a-f]{6}$/.test(hex)) return `#${hex.toUpperCase()}`;
  if (/^[0-9a-f]{8}$/.test(hex)) return `#${hex.slice(2).toUpperCase()}`;
  return fallback;
}
