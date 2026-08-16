import { Memory } from '@/src/types/memory.types';
import ActionItems from './action-items';
import MemoryEvents from '../events/memory-events';
import Plugins from '../plugins/plugins';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  const overview = (memory?.structured?.overview || '').trim();

  return (
    <div className="flex flex-col gap-12">
      {overview && (
        <div className="mt-8 md:mt-10">
          <p className="whitespace-pre-wrap text-base leading-7 text-zinc-200 md:text-lg">
            {overview}
          </p>
        </div>
      )}

      {memory.apps_results.length > 0 && (
        <div className={overview ? '' : 'mt-8 md:mt-10'}>
          <Plugins apps={memory.apps_results} />
        </div>
      )}

      {memory?.structured?.events?.length > 0 && (
        <div>
          <MemoryEvents events={memory.structured.events} />
        </div>
      )}

      {memory?.structured?.action_items?.length > 0 && (
        <div>
          <ActionItems items={memory.structured.action_items} />
        </div>
      )}
    </div>
  );
}
