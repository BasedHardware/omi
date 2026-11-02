'use client';

import { AudioLines } from 'lucide-react';
import {
  presentableNoteSection,
  resolvableNoteSources,
} from '@omi/note-shared/note-sources.mjs';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { splitNoteSections, type NoteSectionInput } from '@/lib/meetingNotes';

const NOTE_MARKDOWN_CLASS = cn(
  'prose prose-invert max-w-none text-base leading-[1.65] text-text-secondary',
  'prose-headings:mb-2 prose-headings:mt-4 prose-headings:font-semibold prose-headings:text-text-primary first:prose-headings:mt-0',
  'prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-1',
  'prose-li:marker:text-text-quaternary prose-strong:text-text-primary',
  '[&_li_li]:text-text-tertiary [&_li>ul]:pl-5 [&_li>ol]:pl-5',
);

const NOTE_MARKDOWN_QUIET_CLASS = cn(
  'prose prose-invert max-w-none text-sm leading-relaxed text-text-tertiary',
  'prose-headings:mb-2 prose-headings:mt-3 prose-headings:font-semibold prose-headings:text-text-secondary first:prose-headings:mt-0',
  'prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5',
  'prose-li:marker:text-text-quaternary prose-strong:text-text-secondary',
  '[&_li>ul]:pl-5 [&_li>ol]:pl-5',
);

function NoteMarkdown({ body, quiet }: { body: string; quiet?: boolean }) {
  return (
    <div className={quiet ? NOTE_MARKDOWN_QUIET_CLASS : NOTE_MARKDOWN_CLASS}>
      <ReactMarkdown>{body}</ReactMarkdown>
    </div>
  );
}

interface NoteSectionsProps {
  sections: NoteSectionInput[];
  transcriptSegments?: { id?: string | null; start: number }[];
  onOpenSource?: (id: string) => void;
}

export function NoteSections({
  sections,
  transcriptSegments = [],
  onOpenSource,
}: NoteSectionsProps) {
  const transcriptIDs = transcriptSegments.flatMap((segment) =>
    segment.id ? [segment.id] : [],
  );
  // Inline citations the repair removes become the section's source control, so a legacy
  // note whose only evidence was `[s01234]` keeps its pointer to the transcript.
  const presentable = sections.map((section) =>
    presentableNoteSection(section, transcriptIDs),
  );
  const { mains, sideNotes } = splitNoteSections(presentable);

  // One quiet control per section, beside its heading, instead of a row of timestamps under
  // the prose. It opens the transcript at the section's first resolvable source.
  const sourcesButton = (heading: string, sourceIDs?: string[] | null) => {
    if (!onOpenSource) return null;
    const first = resolvableNoteSources(sourceIDs ?? [], transcriptIDs).find((id) => {
      const segment = transcriptSegments.find((segment) => segment.id === id);
      return segment && Number.isFinite(segment.start) && segment.start >= 0;
    });
    if (!first) return null;
    return (
      <button
        type="button"
        title="Show in transcript"
        aria-label={heading ? `Show ${heading} in transcript` : 'Show in transcript'}
        onClick={() => onOpenSource(first)}
        className="-mr-1.5 shrink-0 rounded-md p-1.5 text-text-tertiary opacity-60 transition-opacity hover:text-text-secondary hover:opacity-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 group-hover:opacity-100"
      >
        <AudioLines aria-hidden="true" className="h-4 w-4" />
      </button>
    );
  };

  const sectionHeader = (heading: string | undefined, sourceIDs?: string[] | null) => {
    const button = sourcesButton(heading ?? '', sourceIDs);
    if (!heading && !button) return null;
    return (
      <div className={cn('mb-2 flex items-start gap-2', !heading && 'justify-end')}>
        {heading ? (
          <h2 className="flex-1 text-lg font-semibold text-text-primary">{heading}</h2>
        ) : null}
        {button}
      </div>
    );
  };

  return (
    <div>
      {mains.map((section, index) => {
        const heading = section.heading?.trim();
        const body = section.body_markdown?.trim();
        return (
          <section key={index} className={cn('group', index > 0 && 'mt-6')}>
            {sectionHeader(heading, section.source_segment_ids)}
            {body ? <NoteMarkdown body={body} /> : null}
          </section>
        );
      })}
      {sideNotes.length > 0 && (
        <aside className="mt-6 rounded-xl border border-bg-quaternary/50 bg-bg-secondary p-4">
          {sideNotes.map((section, index) => {
            const heading = section.heading?.trim() || 'Side notes';
            const body = section.body_markdown?.trim();
            return (
              <div key={index} className={cn('group', index > 0 && 'mt-4')}>
                {sectionHeader(heading, section.source_segment_ids)}
                {body ? <NoteMarkdown body={body} quiet /> : null}
              </div>
            );
          })}
        </aside>
      )}
    </div>
  );
}
