'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { getApp } from '@/lib/api';
import type { AppResponse } from '@/types/conversation';
import type { App } from '@/types/apps';

/**
 * Parse markdown content into sections based on h2 headers
 * Returns an array of { title, content } objects
 */
function parseMarkdownSections(
  content: string,
): { title: string | null; content: string }[] {
  const lines = content.split('\n');
  const sections: { title: string | null; content: string }[] = [];
  let currentSection: { title: string | null; content: string[] } = {
    title: null,
    content: [],
  };

  for (const line of lines) {
    // Check for ## headers (h2)
    const h2Match = line.match(/^##\s+(.+)$/);
    if (h2Match) {
      // Save previous section if it has content
      if (currentSection.content.length > 0 || currentSection.title) {
        sections.push({
          title: currentSection.title,
          content: currentSection.content.join('\n').trim(),
        });
      }
      // Start new section
      currentSection = { title: h2Match[1], content: [] };
    } else {
      currentSection.content.push(line);
    }
  }

  // Don't forget the last section
  if (currentSection.content.length > 0 || currentSection.title) {
    sections.push({
      title: currentSection.title,
      content: currentSection.content.join('\n').trim(),
    });
  }

  return sections;
}

interface AppSummaryCardProps {
  appResponse: AppResponse;
  className?: string;
}

export function AppSummaryCard({ appResponse, className }: AppSummaryCardProps) {
  const [app, setApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);
  const [isDeleted, setIsDeleted] = useState(false);

  // Parse content into sections
  const sections = useMemo(() => {
    return parseMarkdownSections(appResponse.content || '');
  }, [appResponse.content]);

  // Check if content has multiple sections (h2 headers)
  const hasMultipleSections =
    sections.length > 1 || (sections.length === 1 && sections[0].title);

  useEffect(() => {
    async function fetchAppInfo() {
      if (!appResponse.app_id) {
        setLoading(false);
        return;
      }

      try {
        const appInfo = await getApp(appResponse.app_id);
        setApp(appInfo);
      } catch (error: unknown) {
        // Check for 404 (deleted template) - don't log as error
        const errorMessage = error instanceof Error ? error.message : String(error);
        if (errorMessage.includes('404')) {
          setIsDeleted(true);
        } else {
          console.error('Failed to fetch app info:', error);
        }
      } finally {
        setLoading(false);
      }
    }

    fetchAppInfo();
  }, [appResponse.app_id]);

  if (!appResponse.content) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'noise-overlay rounded-xl p-4',
        'border border-white/[0.06] bg-white/[0.02]',
        className,
      )}
    >
      {/* App Header */}
      <div className="mb-3 flex items-center gap-3">
        {loading ? (
          <div className="h-8 w-8 animate-pulse rounded-lg bg-bg-quaternary" />
        ) : isDeleted ? (
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-bg-quaternary">
            <Sparkles className="h-4 w-4 text-text-tertiary" />
          </div>
        ) : app?.image ? (
          <img
            src={app.image}
            alt={app.name}
            className="h-8 w-8 rounded-lg object-cover"
          />
        ) : (
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.14]">
            <Sparkles className="h-4 w-4 text-text-primary" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-sm font-medium text-text-primary">
            {loading ? (
              <span className="text-text-tertiary">Loading...</span>
            ) : isDeleted ? (
              <span className="italic text-text-tertiary">
                Template no longer available
              </span>
            ) : (
              app?.name || 'App Summary'
            )}
          </h4>
          {!isDeleted && app?.description && (
            <p className="truncate text-xs text-text-tertiary">{app.description}</p>
          )}
        </div>
      </div>

      {/* Summary Content - Sectioned or Plain */}
      {hasMultipleSections ? (
        <div className="space-y-4">
          {sections.map((section, index) => (
            <div
              key={index}
              className="rounded-lg border border-white/[0.08] bg-gradient-to-b from-white/[0.06] to-white/[0.02] p-3"
            >
              {section.title && (
                <h3 className="mb-2 text-sm font-medium text-text-primary">
                  {section.title}
                </h3>
              )}
              {section.content && (
                <div className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed text-text-secondary prose-headings:font-medium prose-headings:text-text-primary prose-h3:mb-2 prose-h3:mt-4 prose-h3:text-xs prose-p:my-3 prose-strong:text-text-primary prose-code:rounded prose-code:bg-bg-quaternary prose-code:px-1 prose-code:py-0.5 prose-code:text-text-primary prose-ul:my-3 prose-li:my-1.5">
                  <ReactMarkdown>{section.content}</ReactMarkdown>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed text-text-secondary prose-headings:font-medium prose-headings:text-text-primary prose-h2:mb-3 prose-h2:mt-5 prose-h2:text-base prose-h3:mb-2 prose-h3:mt-4 prose-h3:text-sm prose-p:my-3 prose-strong:text-text-primary prose-code:rounded prose-code:bg-bg-quaternary prose-code:px-1 prose-code:py-0.5 prose-code:text-text-primary prose-ul:my-3 prose-li:my-1.5">
          <ReactMarkdown>{appResponse.content}</ReactMarkdown>
        </div>
      )}
    </motion.div>
  );
}

/**
 * Loading skeleton for AppSummaryCard
 */
export function AppSummaryCardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-bg-quaternary/50 bg-bg-tertiary p-4">
      <div className="mb-3 flex items-center gap-3">
        <div className="h-8 w-8 rounded-lg bg-bg-quaternary" />
        <div className="flex-1">
          <div className="h-4 w-24 rounded bg-bg-quaternary" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-bg-quaternary" />
        <div className="h-3 w-5/6 rounded bg-bg-quaternary" />
        <div className="h-3 w-4/6 rounded bg-bg-quaternary" />
      </div>
    </div>
  );
}
