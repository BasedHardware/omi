'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { GenerativeMarkdown } from './GenerativeMarkdown';

interface SummarySection {
  title: string;
  content: string;
}

/**
 * Detect if content is a template-style numbered summary.
 * Looks for patterns like:
 * 1. Section title:
 *    - bullet points
 * 2. Another section:
 *    - bullet points
 */
function parseSections(text: string): SummarySection[] | null {
  // Match "1. Title:" or "1. **Title**:" patterns
  const sectionPattern = /^(\d+)\.\s+(?:\*\*)?(.+?)(?:\*\*)?:\s*$/gm;
  const matches = [...text.matchAll(sectionPattern)];

  if (matches.length < 2) return null; // Need at least 2 sections to be worth collapsing

  const sections: SummarySection[] = [];

  for (let i = 0; i < matches.length; i++) {
    const match = matches[i];
    const title = match[2].trim();
    const start = match.index! + match[0].length;
    const end = i < matches.length - 1 ? matches[i + 1].index! : text.length;
    const content = text.slice(start, end).trim();

    if (title && content) {
      sections.push({ title, content });
    }
  }

  // Also extract any intro text before the first numbered section
  if (matches.length > 0 && matches[0].index! > 0) {
    const intro = text.slice(0, matches[0].index!).trim();
    if (intro) {
      sections.unshift({ title: '', content: intro });
    }
  }

  return sections.length >= 2 ? sections : null;
}

interface CollapsibleSummaryProps {
  content: string;
  className?: string;
  /** Max lines to show before collapsing (for non-sectioned content) */
  maxLines?: number;
}

export function CollapsibleSummary({ content, className, maxLines = 6 }: CollapsibleSummaryProps) {
  const sections = parseSections(content);

  if (sections) {
    return <SectionedSummary sections={sections} className={className} />;
  }

  // For non-template content, use simple truncation
  return <TruncatedSummary content={content} className={className} maxLines={maxLines} />;
}

/**
 * Renders structured sections as collapsible accordion-style cards.
 * First section (or intro) is always visible.
 */
function SectionedSummary({ sections, className }: { sections: SummarySection[]; className?: string }) {
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set([0]));

  const toggle = (index: number) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  // Separate intro (untitled section) from numbered sections
  const intro = sections[0]?.title === '' ? sections[0] : null;
  const numberedSections = intro ? sections.slice(1) : sections;

  return (
    <div className={cn('space-y-3', className)}>
      {/* Intro text (always visible) */}
      {intro && (
        <GenerativeMarkdown content={intro.content} className="text-text-secondary leading-relaxed" />
      )}

      {/* Numbered sections as compact cards */}
      <div className="rounded-xl border border-border overflow-hidden">
        {numberedSections.map((section, i) => {
          const isOpen = expandedSections.has(intro ? i + 1 : i);
          return (
            <div key={i} className={cn(i > 0 && 'border-t border-border')}>
              <button
                onClick={() => toggle(intro ? i + 1 : i)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/30 transition-colors"
              >
                <span className="text-xs text-muted-foreground font-mono w-5 flex-shrink-0">
                  {i + 1}.
                </span>
                <span className="text-sm font-medium text-foreground flex-1 truncate">
                  {section.title}
                </span>
                <ChevronDown
                  className={cn(
                    'w-4 h-4 text-muted-foreground flex-shrink-0 transition-transform duration-200',
                    isOpen && 'rotate-180'
                  )}
                />
              </button>
              <div
                className={cn(
                  'grid transition-[grid-template-rows] duration-200 ease-out',
                  isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
                )}
              >
                <div className="overflow-hidden">
                  <div className="px-4 pb-3 pl-12">
                    <GenerativeMarkdown content={section.content} className="text-sm text-text-secondary" />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Simple truncation for non-sectioned summaries.
 */
function TruncatedSummary({ content, className, maxLines }: { content: string; className?: string; maxLines: number }) {
  const [expanded, setExpanded] = useState(false);
  const lines = content.split('\n');
  const isLong = lines.length > maxLines;

  return (
    <div className={className}>
      <div className={cn(!expanded && isLong && 'relative')}>
        <div className={cn(!expanded && isLong && `line-clamp-[${maxLines}]`)}>
          <GenerativeMarkdown content={expanded || !isLong ? content : lines.slice(0, maxLines).join('\n')} />
        </div>
        {!expanded && isLong && (
          <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-bg-primary to-transparent" />
        )}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors"
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}
