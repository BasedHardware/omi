import { Events } from '@/src/types/memory.types';
import { eventFacts } from '@/src/lib/shared-note.mjs';

interface MemoryEventsProps {
  events: Events[];
}
export default function MemoryEvents({ events }: MemoryEventsProps) {
  return (
    <div>
      <h2 className="sn-h3">Events</h2>
      <ul className="sn-events">
        {events.map((event, index) => {
          const { title, description, start, end, duration } = eventFacts(event);
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
