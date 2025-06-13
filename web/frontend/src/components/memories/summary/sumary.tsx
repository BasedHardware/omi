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
      <div className="mt-8 px-6 md:mt-10 md:px-12">
        <div className="space-y-4">
          <h3 className="text-xl font-semibold tracking-tight text-white md:text-2xl">Overview</h3>
          {memory.structured.overview ? (
            <p className="text-base leading-relaxed text-zinc-300 md:text-lg">
              {memory.structured.overview}
            </p>
          ) : (
            <div className="rounded-lg border border-dashed border-zinc-700/50 bg-zinc-900/50 p-4 text-center">
              <p className="text-sm text-zinc-500">No overview available for this memory.</p>
            </div>
          )}
        </div>
      </div>

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

      {memory.apps_results.length > 0 && (
        <div className="px-6 md:px-12">
          <Plugins apps={memory.apps_results} />
        </div>
      )}
    </div>
  );
}
