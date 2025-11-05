import { Memory } from '@/src/types/memory.types';
import ActionItems from './action-items';
import MemoryEvents from '../events/memory-events';
import Plugins from '../plugins/plugins';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  return (
    <div className="flex flex-col gap-12">
      {memory.apps_results.length > 0 && (
        <div className="mt-8 px-6 md:mt-10 md:px-12">
          <Plugins apps={memory.apps_results} />
        </div>
      )}

      {memory?.structured?.action_items?.length > 0 && (
        <div className="px-6 md:px-12">
          <ActionItems items={memory.structured.action_items} />
        </div>
      )}

      {memory?.structured?.events?.length > 0 && (
        <div className="px-6 md:px-12">
          <MemoryEvents events={memory.structured.events} />
        </div>
      )}
    </div>
  );
}
