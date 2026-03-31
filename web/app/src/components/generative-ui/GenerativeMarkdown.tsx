'use client';

import { useState } from 'react';
import Markdown from 'react-markdown';
import {
  ChevronDown,
  ChevronUp,
  Quote,
  ListChecks,
  Clock,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Search,
  CircleDot,
  GraduationCap,
  Workflow,
  ExternalLink,
  FileText,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  parseGenerativeContent,
  type ParsedSegment,
  type QuoteBoardSegment,
  type FollowupsSegment,
  type AccordionSegment,
  type TimelineSegment,
  type HighlightSegment,
  type TableSegment,
  type PieChartSegment,
  type TaskSegment,
  type FlowSegment,
  type StudySegment,
  type RichListSegment,
} from './parser';

// ============================================================================
// Color helpers
// ============================================================================

const namedColors: Record<string, string> = {
  yellow: '#F9D71C',
  orange: '#F97316',
  green: '#22C55E',
  blue: '#3B82F6',
  purple: '#8B5CF6',
  red: '#EF4444',
  pink: '#EC4899',
  cyan: '#06B6D4',
  amber: '#F59E0B',
  lime: '#84CC16',
  teal: '#14B8A6',
  indigo: '#6366F1',
};

function resolveColor(color?: string, fallback = '#3B82F6'): string {
  if (!color) return fallback;
  const c = color.trim().toLowerCase();
  if (namedColors[c]) return namedColors[c];
  if (c.startsWith('#')) return c;
  if (/^[0-9a-f]{6}$/i.test(c)) return `#${c}`;
  return fallback;
}

const recordStatusColor: Record<string, string> = {
  'on the record': '#22C55E',
  background: '#F59E0B',
  'off the record': '#EF4444',
};

const followupTypeColor: Record<string, string> = {
  'fact-check': '#F97316',
  verification: '#3B82F6',
  question: '#8B5CF6',
};

const followupTypeIcon: Record<string, React.ReactNode> = {
  'fact-check': <Search className="w-3.5 h-3.5" />,
  verification: <CheckCircle2 className="w-3.5 h-3.5" />,
  question: <HelpCircle className="w-3.5 h-3.5" />,
};

const timelineLabelColor: Record<string, string> = {
  context: '#3B82F6',
  conflict: '#EF4444',
  claim: '#F59E0B',
  decision: '#22C55E',
  reaction: '#8B5CF6',
  'human impact': '#EC4899',
  'next steps': '#06B6D4',
};

const chartPalette = [
  '#8B5CF6', '#22C55E', '#F97316', '#3B82F6', '#EF4444',
  '#A78BFA', '#06B6D4', '#EA580C',
];

// ============================================================================
// Quote Board
// ============================================================================

function QuoteBoardWidget({ segment }: { segment: QuoteBoardSegment }) {
  const [expanded, setExpanded] = useState(false);
  const visibleQuotes = expanded ? segment.quotes : segment.quotes.slice(0, 3);

  return (
    <div className="rounded-2xl border border-border bg-card p-4 my-3">
      <div className="flex items-center gap-2 mb-3">
        <Quote className="w-4 h-4 text-primary" />
        <h4 className="text-sm font-semibold text-foreground">Key Quotes</h4>
      </div>
      <div className="space-y-3">
        {visibleQuotes.map((q, i) => (
          <div key={i} className="rounded-xl bg-secondary/50 p-3">
            <p className="text-sm text-foreground leading-relaxed italic">
              &ldquo;{q.text}&rdquo;
            </p>
            <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/80">{q.speaker}</span>
              {q.time && <span>· {q.time}</span>}
              {q.record && (
                <span
                  className="px-1.5 py-0.5 rounded-full text-[10px] font-medium"
                  style={{
                    backgroundColor: `${recordStatusColor[q.record.toLowerCase()] || '#6B7280'}20`,
                    color: recordStatusColor[q.record.toLowerCase()] || '#6B7280',
                  }}
                >
                  {q.record}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      {segment.quotes.length > 3 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
        >
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {expanded ? 'Show less' : `Show ${segment.quotes.length - 3} more`}
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Followups
// ============================================================================

function FollowupsWidget({ segment }: { segment: FollowupsSegment }) {
  const [expanded, setExpanded] = useState(false);
  const visibleItems = expanded ? segment.items : segment.items.slice(0, 3);

  return (
    <div className="rounded-2xl border border-border bg-card p-4 my-3">
      <div className="flex items-center gap-2 mb-3">
        <ListChecks className="w-4 h-4 text-primary" />
        <h4 className="text-sm font-semibold text-foreground">Follow-ups & Fact-checks</h4>
      </div>
      <div className="space-y-2">
        {visibleItems.map((item, i) => {
          const color = (item.type && followupTypeColor[item.type]) || '#6B7280';
          const icon = item.type && followupTypeIcon[item.type];
          return (
            <div key={i} className="flex items-start gap-3 py-2">
              <div
                className="mt-1.5 w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-foreground leading-relaxed">{item.text}</p>
                {item.type && (
                  <span
                    className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium"
                    style={{
                      backgroundColor: `${color}15`,
                      color,
                    }}
                  >
                    {icon}
                    {item.type}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {segment.items.length > 3 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
        >
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {expanded ? 'Show less' : `Show ${segment.items.length - 3} more`}
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Accordion
// ============================================================================

function AccordionWidget({ segment }: { segment: AccordionSegment }) {
  const [openSections, setOpenSections] = useState<Set<number>>(new Set());

  const toggle = (index: number) => {
    setOpenSections((prev) => {
      const next = new Set(segment.allowMultiple ? prev : []);
      if (prev.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  return (
    <div className="rounded-2xl border border-border bg-card my-3 overflow-hidden">
      {segment.title && (
        <div className="px-4 py-3 border-b border-border">
          <h4 className="text-sm font-semibold text-foreground">{segment.title}</h4>
        </div>
      )}
      {segment.sections.map((section, i) => {
        const isOpen = openSections.has(i);
        return (
          <div key={i} className={cn(i > 0 && 'border-t border-border')}>
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-secondary/30 transition-colors"
            >
              <span className="text-sm font-medium text-foreground">{section.title}</span>
              {isOpen ? (
                <ChevronUp className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              )}
            </button>
            {isOpen && (
              <div className="px-4 pb-3">
                <div className="prose prose-invert prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                  <Markdown>{section.content}</Markdown>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// Timeline
// ============================================================================

function TimelineWidget({ segment }: { segment: TimelineSegment }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 my-3">
      {segment.title && (
        <div className="flex items-center gap-2 mb-3">
          <Clock className="w-4 h-4 text-primary" />
          <h4 className="text-sm font-semibold text-foreground">{segment.title}</h4>
        </div>
      )}
      <div className="relative pl-6">
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />
        {segment.events.map((event, i) => {
          const color =
            event.label && timelineLabelColor[event.label.toLowerCase()]
              ? timelineLabelColor[event.label.toLowerCase()]
              : '#3B82F6';
          return (
            <div key={i} className="relative pb-4 last:pb-0">
              <div
                className="absolute -left-6 top-1.5 w-3.5 h-3.5 rounded-full border-2 border-card"
                style={{ backgroundColor: color }}
              />
              <div className="flex items-center gap-2 mb-0.5">
                {event.time && (
                  <span className="text-xs text-muted-foreground font-mono">{event.time}</span>
                )}
                {event.label && (
                  <span
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                    style={{ backgroundColor: `${color}20`, color }}
                  >
                    {event.label}
                  </span>
                )}
              </div>
              <p className="text-sm text-foreground leading-relaxed">{event.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Highlight
// ============================================================================

function HighlightWidget({ segment }: { segment: HighlightSegment }) {
  const color = resolveColor(segment.color, '#F9D71C');
  return (
    <span
      className="rounded px-1 py-0.5"
      style={{ backgroundColor: `${color}30`, color }}
    >
      {segment.text}
    </span>
  );
}

// ============================================================================
// Table
// ============================================================================

function TableWidget({ segment }: { segment: TableSegment }) {
  const isHeader = segment.rows.length > 1;

  return (
    <div className="rounded-2xl border border-border bg-card my-3 overflow-hidden">
      {segment.title && (
        <div className="px-4 py-3 border-b border-border">
          <h4 className="text-sm font-semibold text-foreground">{segment.title}</h4>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          {isHeader && (
            <thead>
              <tr className="border-b border-border bg-secondary/30">
                {segment.rows[0].map((cell, ci) => (
                  <th key={ci} className="px-4 py-2 text-left font-medium text-foreground">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {(isHeader ? segment.rows.slice(1) : segment.rows).map((row, ri) => (
              <tr key={ri} className="border-b border-border last:border-0">
                {row.map((cell, ci) => (
                  <td key={ci} className="px-4 py-2 text-muted-foreground">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================================
// Pie/Bar Chart (simple CSS-only)
// ============================================================================

function ChartWidget({ segment }: { segment: PieChartSegment }) {
  const total = segment.segments.reduce((sum, s) => sum + s.value, 0);

  return (
    <div className="rounded-2xl border border-border bg-card p-4 my-3">
      {segment.title && (
        <h4 className="text-sm font-semibold text-foreground mb-3">{segment.title}</h4>
      )}
      {segment.chartType === 'bar' ? (
        <div className="space-y-2">
          {segment.segments.map((s, i) => {
            const color = resolveColor(s.color, chartPalette[i % chartPalette.length]);
            const pct = total > 0 ? (s.value / total) * 100 : 0;
            return (
              <div key={i}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-foreground">{s.label}</span>
                  <span className="text-muted-foreground">{s.value}</span>
                </div>
                <div className="h-2 rounded-full bg-secondary overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${pct}%`, backgroundColor: color }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Pie / Donut — render as legend + colored segments (CSS conic gradient) */
        <div className="flex items-center gap-6">
          <div
            className="w-24 h-24 rounded-full flex-shrink-0"
            style={{
              background: `conic-gradient(${segment.segments
                .map((s, i) => {
                  const color = resolveColor(s.color, chartPalette[i % chartPalette.length]);
                  const startPct =
                    segment.segments.slice(0, i).reduce((sum, x) => sum + x.value, 0) /
                    total *
                    100;
                  const endPct = startPct + (s.value / total) * 100;
                  return `${color} ${startPct}% ${endPct}%`;
                })
                .join(', ')})`,
              ...(segment.chartType === 'donut'
                ? {
                    WebkitMask: 'radial-gradient(farthest-side, transparent 55%, #000 56%)',
                    mask: 'radial-gradient(farthest-side, transparent 55%, #000 56%)',
                  }
                : {}),
            }}
          />
          <div className="space-y-1">
            {segment.segments.map((s, i) => {
              const color = resolveColor(s.color, chartPalette[i % chartPalette.length]);
              const pct = total > 0 ? Math.round((s.value / total) * 100) : 0;
              return (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-foreground">{s.label}</span>
                  <span className="text-muted-foreground">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Task
// ============================================================================

const priorityColor: Record<string, string> = {
  high: '#EF4444',
  medium: '#F59E0B',
  low: '#22C55E',
};

function TaskWidget({ segment }: { segment: TaskSegment }) {
  const [expanded, setExpanded] = useState(false);
  const color = priorityColor[segment.priority || 'medium'] || '#F59E0B';

  return (
    <div className="rounded-2xl border border-border bg-card p-4 my-3">
      <div className="flex items-start gap-3">
        <div
          className="mt-1.5 w-2.5 h-2.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-foreground">{segment.title}</h4>
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground flex-shrink-0">
              {segment.priority && (
                <span
                  className="px-1.5 py-0.5 rounded-full font-medium capitalize"
                  style={{ backgroundColor: `${color}20`, color }}
                >
                  {segment.priority}
                </span>
              )}
              {segment.steps.length > 0 && <span>{segment.steps.length} steps</span>}
            </div>
          </div>

          {segment.summary && (
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">{segment.summary}</p>
          )}

          {segment.steps.length > 0 && (
            <div className={cn('mt-3 space-y-1.5', !expanded && segment.steps.length > 3 && 'max-h-[100px] overflow-hidden relative')}>
              {(expanded ? segment.steps : segment.steps.slice(0, 3)).map((step, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-xs text-muted-foreground font-mono mt-0.5 w-5 flex-shrink-0">{i + 1}.</span>
                  <p className="text-sm text-foreground">{step.title}</p>
                </div>
              ))}
              {!expanded && segment.steps.length > 3 && (
                <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-card to-transparent" />
              )}
            </div>
          )}

          {segment.steps.length > 3 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 text-xs text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
            >
              {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {expanded ? 'Show less' : `Show all ${segment.steps.length} steps`}
            </button>
          )}

          {segment.refs.length > 0 && (
            <div className="mt-3 pt-2 border-t border-border">
              {segment.refs.map((ref, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <FileText className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>
                    {ref.by && <span className="font-medium text-foreground/70">{ref.by}: </span>}
                    {ref.text}
                    {ref.time && <span className="ml-1 opacity-60">({ref.time})</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Flow
// ============================================================================

function FlowWidget({ segment }: { segment: FlowSegment }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 my-3">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Workflow className="w-4 h-4 text-primary" />
          <h4 className="text-sm font-semibold text-foreground">{segment.title}</h4>
        </div>
        <span className="text-xs text-muted-foreground">{segment.steps.length} steps</span>
      </div>
      <div className="relative pl-6">
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />
        {segment.steps.map((step, i) => {
          const isException = step.type === 'exception';
          return (
            <div key={i} className="relative pb-3 last:pb-0">
              <div
                className={cn(
                  'absolute -left-6 top-1.5 w-3.5 h-3.5 rounded-full border-2 border-card',
                  isException ? 'bg-amber-500' : 'bg-primary'
                )}
              />
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-xs text-muted-foreground font-mono">Step {i + 1}</span>
                {isException && (
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-500">
                    Exception
                  </span>
                )}
              </div>
              <p className="text-sm text-foreground leading-relaxed">{step.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Study
// ============================================================================

function StudyWidget({ segment }: { segment: StudySegment }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const q = segment.questions[currentIndex];

  return (
    <div className="rounded-2xl border border-primary/30 bg-gradient-to-br from-primary/10 to-primary/5 p-4 my-3">
      <div className="flex items-center gap-2 mb-3">
        <GraduationCap className="w-4 h-4 text-primary" />
        <h4 className="text-sm font-semibold text-foreground">{segment.title || 'Study Mode'}</h4>
        <span className="text-xs text-muted-foreground ml-auto">
          {currentIndex + 1}/{segment.questions.length}
        </span>
      </div>

      <div className="bg-card/50 rounded-xl p-4 min-h-[80px]">
        <p className="text-sm text-foreground font-medium mb-3">{q.question}</p>
        {showAnswer ? (
          <div className="text-sm text-primary bg-primary/10 rounded-lg p-3">
            {q.answer}
          </div>
        ) : (
          <button
            onClick={() => setShowAnswer(true)}
            className="text-xs text-primary hover:text-primary/80 transition-colors"
          >
            Show answer
          </button>
        )}
      </div>

      {segment.questions.length > 1 && (
        <div className="flex items-center justify-between mt-3">
          <button
            onClick={() => { setCurrentIndex(Math.max(0, currentIndex - 1)); setShowAnswer(false); }}
            disabled={currentIndex === 0}
            className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
          >
            Previous
          </button>
          <button
            onClick={() => { setCurrentIndex(Math.min(segment.questions.length - 1, currentIndex + 1)); setShowAnswer(false); }}
            disabled={currentIndex === segment.questions.length - 1}
            className="text-xs text-primary hover:text-primary/80 disabled:opacity-30 transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Rich List
// ============================================================================

function RichListWidget({ segment }: { segment: RichListSegment }) {
  return (
    <div className="my-3 -mx-1 overflow-x-auto">
      <div className="flex gap-3 px-1 w-max">
        {segment.items.map((item, i) => (
          <a
            key={i}
            href={item.url || undefined}
            target={item.url ? '_blank' : undefined}
            rel={item.url ? 'noopener noreferrer' : undefined}
            className={cn(
              'w-48 rounded-xl bg-card border border-border overflow-hidden flex-shrink-0',
              item.url && 'hover:border-primary/30 transition-colors cursor-pointer'
            )}
          >
            {item.thumb && (
              <div className="h-28 bg-secondary">
                <img src={item.thumb} alt={item.title} className="w-full h-full object-cover" />
              </div>
            )}
            <div className="p-3">
              <p className="text-sm font-medium text-foreground truncate">{item.title}</p>
              {item.description && (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{item.description}</p>
              )}
              {item.url && (
                <div className="flex items-center gap-1 mt-2 text-[10px] text-primary">
                  <ExternalLink className="w-3 h-3" />
                  <span>Open</span>
                </div>
              )}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

function renderSegment(segment: ParsedSegment, index: number) {
  switch (segment.type) {
    case 'markdown':
      return (
        <div
          key={index}
          className="prose prose-invert prose-sm max-w-none leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
        >
          <Markdown>{(segment as { content: string }).content}</Markdown>
        </div>
      );
    case 'quote-board':
      return <QuoteBoardWidget key={index} segment={segment as QuoteBoardSegment} />;
    case 'followups':
      return <FollowupsWidget key={index} segment={segment as FollowupsSegment} />;
    case 'accordion':
      return <AccordionWidget key={index} segment={segment as AccordionSegment} />;
    case 'timeline':
      return <TimelineWidget key={index} segment={segment as TimelineSegment} />;
    case 'highlight':
      return <HighlightWidget key={index} segment={segment as HighlightSegment} />;
    case 'table':
      return <TableWidget key={index} segment={segment as TableSegment} />;
    case 'pie-chart':
      return <ChartWidget key={index} segment={segment as PieChartSegment} />;
    case 'task':
      return <TaskWidget key={index} segment={segment as TaskSegment} />;
    case 'flow':
      return <FlowWidget key={index} segment={segment as FlowSegment} />;
    case 'study':
      return <StudyWidget key={index} segment={segment as StudySegment} />;
    case 'rich-list':
      return <RichListWidget key={index} segment={segment as RichListSegment} />;
    default:
      return null;
  }
}

interface GenerativeMarkdownProps {
  content: string;
  className?: string;
}

export function GenerativeMarkdown({ content, className }: GenerativeMarkdownProps) {
  const segments = parseGenerativeContent(content);

  // Fast path: pure markdown
  if (segments.length === 1 && segments[0].type === 'markdown') {
    return (
      <div
        className={cn(
          'prose prose-invert prose-sm max-w-none leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
          className
        )}
      >
        <Markdown>{content}</Markdown>
      </div>
    );
  }

  return <div className={className}>{segments.map(renderSegment)}</div>;
}
