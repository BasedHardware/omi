import { Memory, SharedScreenshotsResult } from '@/src/types/memory.types';
import { assignSectionIds, splitSections } from '@/src/lib/shared-note.mjs';
import ActionItems from './action-items';
import ScreenMoments from './screen-moments';
import MemoryEvents from '../events/memory-events';
import Plugins from '../plugins/plugins';
import Markdown from 'markdown-to-jsx';
import {
  presentableNoteSection,
  resolvableNoteSources,
} from '@omi/note-shared/note-sources.mjs';
import { repairNoteCitations } from '@omi/note-shared/note-citations.mjs';

interface SummaryProps {
  memory: Memory;
  onOpenSource?: (id: string) => void;
  screenshots?: SharedScreenshotsResult | null;
}

export default function Summary({
  memory,
  screenshots = null,
  onOpenSource,
}: SummaryProps) {
  const knownIDs = (memory.transcript_segments ?? []).flatMap((segment) =>
    segment.id ? [segment.id] : [],
  );
  const overview = repairNoteCitations(
    (memory?.structured?.overview || '').trim(),
    knownIDs,
  ).text;
  // Inline citations the repair removes become source chips (legacy notes whose only
  // evidence was `[s01234]` keep their pointer to the transcript).
  const presentable = memory?.structured?.sections?.map((section) =>
    presentableNoteSection(section, knownIDs),
  );
  const { mains, sideNotes } = splitSections(presentable);
  const ids = assignSectionIds(mains);

  const sourceChip = (sourceIDs?: string[]) => {
    const ids = resolvableNoteSources(sourceIDs, knownIDs);
    if (!ids.length || !onOpenSource) return null;
    return (
      <div className="sn-sources" aria-label="Transcript sources">
        {ids.map((id, index) => (
          <button
            key={id}
            type="button"
            className="sn-source-chip"
            onClick={() => onOpenSource(id)}
            aria-label={`View transcript source ${index + 1} of ${ids.length}`}
          >
            <span aria-hidden="true">❞</span>{' '}
            {index === 0 ? `Sources (${ids.length})` : index + 1}
          </button>
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col">
      {mains.length > 0 ? (
        <>
          {mains.length >= 4 && (
            <nav className="sn-toc" aria-label="In this note">
              <p className="sn-toc-label">In this note</p>
              <ul className="sn-toc-list">
                {mains.map((section, index) => (
                  <li key={ids[index]}>
                    <a href={`#${ids[index]}`}>
                      {section.heading?.trim() || `Section ${index + 1}`}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          )}
          {mains.map((section, index) => {
            const heading = section.heading?.trim();
            const body = section.body_markdown?.trim();
            return (
              <section key={ids[index]} id={ids[index]} className="sn-section">
                {heading ? <h2 className="sn-h2">{heading}</h2> : null}
                {body ? (
                  <Markdown className="sn-md" options={{ forceBlock: true }}>
                    {body}
                  </Markdown>
                ) : null}
                {sourceChip(section.source_segment_ids)}
              </section>
            );
          })}
          {sideNotes.length > 0 && (
            <aside className="sn-aside">
              {sideNotes.map((section, index) => {
                const heading = section.heading?.trim();
                const body = section.body_markdown?.trim();
                return (
                  <div key={index} className="sn-aside-section">
                    {heading ? <h2 className="sn-h3">{heading}</h2> : null}
                    {body ? (
                      <Markdown className="sn-md" options={{ forceBlock: true }}>
                        {body}
                      </Markdown>
                    ) : null}
                    {sourceChip(section.source_segment_ids)}
                  </div>
                );
              })}
            </aside>
          )}
        </>
      ) : (
        overview && (
          <div className="sn-section">
            <Markdown className="sn-md" options={{ forceBlock: true }}>
              {overview}
            </Markdown>
          </div>
        )
      )}

      {memory?.structured?.action_items?.length > 0 && (
        <div className="sn-block">
          <ActionItems items={memory.structured.action_items} knownIDs={knownIDs} />
        </div>
      )}

      {/* Keyed so client navigation between shares never carries state across. */}
      <ScreenMoments
        key={memory.id}
        conversationId={memory.id}
        initial={screenshots}
        startedAt={memory.started_at}
      />

      {memory?.structured?.events?.length > 0 && (
        <div className="sn-block">
          <MemoryEvents events={memory.structured.events} knownIDs={knownIDs} />
        </div>
      )}

      {memory.apps_results.length > 0 && (
        <div className="sn-block">
          <Plugins apps={memory.apps_results} />
        </div>
      )}
    </div>
  );
}
