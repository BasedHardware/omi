import { Memory } from '@/src/types/memory.types';
import ActionItems from './action-items';
import MemoryEvents from '../events/memory-events';
import Puglins from '../plugins/puglins';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  return (
    <div className="flex flex-col gap-10">
      <div className="mt-10">
        <h3 className="text-xl font-semibold md:text-2xl">Overview</h3>
        {!memory.structured.overview ? (
          <p className="mt-3 text-base md:text-lg">{memory.structured.overview}</p>
        ) : (
          <p className="mt-4 text-gray-400">No overview available for this memory.</p>
        )}
      </div>
      {memory.plugins_results.length > 0 && (
        <Puglins puglins={memory.plugins_results} />
      )}
      {memory?.structured?.action_items?.length > 0 && (
        <ActionItems items={memory.structured.action_items} />
      )}
      {memory?.structured?.events?.length > 0 && (
        <MemoryEvents events={memory.structured.events} />
      )}
    </div>
  );
}
