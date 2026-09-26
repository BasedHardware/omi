import { Memory } from '@/src/types/memory.types';
import { assignSectionIds, splitSections } from '@/src/lib/shared-note.mjs';
import ActionItems from './action-items';
import MemoryEvents from '../events/memory-events';
import Plugins from '../plugins/plugins';
import Markdown from 'markdown-to-jsx';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  const overview = (memory?.structured?.overview || '').trim();
  const { mains, sideNotes } = splitSections(memory?.structured?.sections);
  const ids = assignSectionIds(mains);

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
          <ActionItems items={memory.structured.action_items} />
        </div>
      )}

      {memory?.structured?.events?.length > 0 && (
        <div className="sn-block">
          <MemoryEvents events={memory.structured.events} />
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
