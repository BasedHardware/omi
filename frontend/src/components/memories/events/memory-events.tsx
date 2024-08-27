import { Events } from "@/src/types/memory.types";
import { parseTime } from "@/src/utils/parseTime";
import { Clock } from "iconoir-react";
import moment from "moment";

interface MemoryEventsProps {
  events: Events[];
}
export default function MemoryEvents({ events }: MemoryEventsProps){
  return(
      <div>
        <h3 className="text-2xl font-semibold">Events</h3>
        <ul className="mt-3">
          {events.map((event, index) => (
            <li key={index} className="my-5 flex items-start gap-3 first:mt-0">
              <div className="mt-1 w-full">
                <div className="w-full">
                  <div className="flex gap-4 items-center text-zinc-500">
                    <p className="text-sm">{moment(event.start).format('MMMM Do YYYY')}</p>
                    <div className="flex gap-1.5 items-center">
                      <Clock className="min-w-min text-[10px]" />
                      <p className="text-sm">
                        {moment(event.start).format('h:mm a')} - {moment(event.start).add(event.duration, 'minutes').format('h:mm a')}{" "}
                        ({parseTime(event.duration.toString()).trim()})
                      </p>
                    </div>
                  </div>
                  <h2 className="text-lg font-semibold">{event.title}</h2>
                </div>
                <p className="text-zinc-400">{event.description}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
  )
}