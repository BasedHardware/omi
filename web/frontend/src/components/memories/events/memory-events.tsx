import { Events } from '@/src/types/memory.types';
import { parseTime } from '@/src/utils/parseTime';
import { Clock } from 'iconoir-react';
import moment from 'moment';

interface MemoryEventsProps {
  events: Events[];
}
export default function MemoryEvents({ events }: MemoryEventsProps) {
  return (
    <div className="px-4 md:px-12">
      <h3 className="text-xl font-semibold md:text-2xl">Events</h3>
      <ul className="mt-3">
        {events.map((event, index) => (
          <li
            key={index}
            className="my-5 mt-1 flex items-start gap-3 rounded-md border border-solid border-zinc-800 bg-zinc-950 p-3 first:mt-0"
          >
            <div className="w-full">
              <div className="w-full">
                <div className="flex items-center gap-4 text-zinc-500">
                  <p className="text-xs md:text-sm">
                    {moment(event.start).format('MMMM Do YYYY')}
                  </p>
                  <div className="flex items-center gap-1.5">
                    <Clock className="min-w-min text-[10px]" />
                    <p className="text-xs md:text-sm">
                      {moment(event.start).format('h:mm a')} -{' '}
                      {moment(event.start)
                        .add(event.duration, 'minutes')
                        .format('h:mm a')}{' '}
                      ({parseTime(event.duration.toString()).trim()})
                    </p>
                  </div>
                </div>
                <h2 className="mt-2 text-base font-semibold md:text-lg">{event.title}</h2>
              </div>
              <p className="text-sm text-zinc-400 md:text-base">{event.description}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
