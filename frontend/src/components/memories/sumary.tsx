import { Memory } from '@/src/types/memory.types';
import ActionItems from './action-items';
import MemoryEvents from './events/memory-events';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  return (
    <div className="flex flex-col gap-10">
      <div className="mt-10">
        <h3 className="text-xl font-semibold md:text-2xl">Overview</h3>
        <p className="mt-3 text-base md:text-lg">{memory.structured.overview}</p>
      </div>
      {memory?.structured?.action_items?.length > 0 && (
        <ActionItems items={memory.structured.action_items} />
      )}
      {memory?.structured?.events?.length > 0 && (
        <MemoryEvents events={memory.structured.events} />
      )}
    </div>
  );
}
