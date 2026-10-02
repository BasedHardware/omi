import { Events } from '@/src/types/memory.types';
import { parseTime } from '@/src/utils/parseTime';
import moment from 'moment';

interface MemoryEventsProps {
  events: Events[];
}
export default function MemoryEvents({ events }: MemoryEventsProps) {
  return (
    <div>
      <h2 className="sn-h3">Events</h2>
      <ul className="sn-events">
        {events.map((event, index) => (
          <li key={index} className="sn-event">
            <p className="sn-event-title">{event.title}</p>
            <div className="sn-event-meta">
              <span>{moment(event.start).format('MMMM Do YYYY')}</span>
              <span>
                {moment(event.start).format('h:mm a')} -{' '}
                {moment(event.start).add(event.duration, 'minutes').format('h:mm a')} (
                {parseTime(event.duration.toString()).trim()})
              </span>
            </div>
            {event.description ? (
              <p className="sn-event-desc">{event.description}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
