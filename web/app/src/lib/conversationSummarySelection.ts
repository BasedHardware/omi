import type { AppResponse } from '@/types/conversation';

export type ConversationSummaryKind = 'app' | 'overview' | 'sections' | 'empty';

export interface SummarySection {
  heading?: string | null;
  body_markdown?: string | null;
}

export interface SummarySelectionInput {
  structured?: {
    overview?: string | null;
    sections?: SummarySection[] | null;
  };
  apps_results?: AppResponse[] | null;
}

export interface ConversationSummarySelection {
  content: string;
  kind: ConversationSummaryKind;
  appId: string | null;
  resultIndex: number | null;
}

function trimmed(value: string | null | undefined): string {
  return (value ?? '').trim();
}

/** Canonical compatibility Markdown projection for structured sections. */
export function renderSummarySections(
  sections: SummarySection[] | null | undefined,
): string {
  return (sections ?? [])
    .map((section) => {
      const heading = trimmed(section.heading);
      const body = trimmed(section.body_markdown);
      if (!body) return '';
      return heading ? `## ${heading}\n\n${body}` : body;
    })
    .filter(Boolean)
    .join('\n\n');
}

/**
 * Pick the single body used for display, copy, and sharing-adjacent exports.
 * Result identity is the array index, so a legacy app result with a null
 * app_id remains an app result rather than being mistaken for first-party
 * overview content.
 */
export function selectConversationSummary(
  conversation: SummarySelectionInput,
): ConversationSummarySelection {
  const appResults = conversation.apps_results ?? [];
  for (let resultIndex = 0; resultIndex < appResults.length; resultIndex += 1) {
    const result = appResults[resultIndex];
    const content = trimmed(result.content);
    if (content) {
      return {
        content,
        kind: 'app',
        appId: result.app_id ?? null,
        resultIndex,
      };
    }
  }

  const overview = trimmed(conversation.structured?.overview);
  const sections = renderSummarySections(conversation.structured?.sections);
  if (sections && overview === sections) {
    return { content: sections, kind: 'sections', appId: null, resultIndex: null };
  }
  if (overview) {
    return { content: overview, kind: 'overview', appId: null, resultIndex: null };
  }
  if (sections) {
    return { content: sections, kind: 'sections', appId: null, resultIndex: null };
  }
  return { content: '', kind: 'empty', appId: null, resultIndex: null };
}
