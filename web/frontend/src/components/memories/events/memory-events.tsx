import { Events } from '@/src/types/memory.types';
import { eventFacts } from '@/src/lib/shared-note.mjs';
import { presentableNoteText } from '@omi/note-shared/note-sources.mjs';

interface MemoryEventsProps {
  events: Events[];
  knownIDs?: string[];
}
export default function MemoryEvents({ events, knownIDs = [] }: MemoryEventsProps) {
  return (
    <div>
      <h2 className="sn-h3">Events</h2>
      <ul className="sn-events">
        {events.map((event, index) => {
          const facts = eventFacts(event);
          const { start, end, duration } = facts;
          const title = presentableNoteText(facts.title, knownIDs);
          const description = presentableNoteText(facts.description, knownIDs);
          return (
            <li key={index} className="sn-event">
              <p className="sn-event-title">{title || 'Untitled event'}</p>
              <div className="sn-event-meta">
                {start ? (
                  <time dateTime={start.iso}>{start.label}</time>
                ) : (
                  <span>Time unknown</span>
                )}
                {end ? <time dateTime={end.iso}>{end.label}</time> : null}
                {duration ? <span>{duration}</span> : null}
              </div>
              {description ? <p className="sn-event-desc">{description}</p> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
