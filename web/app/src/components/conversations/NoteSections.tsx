'use client';

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
}

export function NoteSections({ sections }: NoteSectionsProps) {
  const { mains, sideNotes } = splitNoteSections(sections);

  return (
    <div>
      {mains.map((section, index) => {
        const heading = section.heading?.trim();
        const body = section.body_markdown?.trim();
        return (
          <section key={index} className={cn(index > 0 && 'mt-8')}>
            {heading ? (
              <h2 className="mb-2 text-lg font-semibold text-text-primary">{heading}</h2>
            ) : null}
            {body ? <NoteMarkdown body={body} /> : null}
          </section>
        );
      })}
      {sideNotes.length > 0 && (
        <aside className="mt-8 rounded-xl border border-bg-quaternary/50 bg-bg-secondary p-4">
          {sideNotes.map((section, index) => {
            const heading = section.heading?.trim() || 'Side notes';
            const body = section.body_markdown?.trim();
            return (
              <div key={index} className={cn(index > 0 && 'mt-4')}>
                <h2 className="mb-2 text-lg font-semibold text-text-primary">
                  {heading}
                </h2>
                {body ? <NoteMarkdown body={body} quiet /> : null}
              </div>
            );
          })}
        </aside>
      )}
    </div>
  );
}
