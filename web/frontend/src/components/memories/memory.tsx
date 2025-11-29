import { Memory as MemoryType } from '@/src/types/memory.types';
import moment from 'moment';
import { SearchParamsTypes } from '@/src/types/params.types';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import MemoryWithTabs from './summary/memory-with-tabs';

interface MemoryProps {
  memory: MemoryType;
  searchParams: SearchParamsTypes;
}

export default function Memory({ memory }: MemoryProps) {
  return (
    <div className="relative text-white">
      {/* Content */}
      <div className="relative z-10">
        <div className="flex flex-col gap-3 pt-6 md:pt-8">
          <h2 className="text-2xl font-medium tracking-wide md:text-3xl">
            {memory.structured.title || DEFAULT_TITLE_MEMORY}
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <time
              dateTime={new Date(memory.created_at).toISOString()}
              className="inline-flex items-center rounded-full bg-zinc-800/50 px-3 py-1 text-xs text-zinc-400 ring-1 ring-inset ring-zinc-800 md:text-sm"
            >
              {(() => {
                const date = moment(memory.created_at);
                const now = moment();
                if (date.isSame(now, 'day')) {
                  return `Today ${date.format('h:mm A')}`;
                } else if (date.isSame(now.clone().subtract(1, 'day'), 'day')) {
                  return `Yesterday ${date.format('h:mm A')}`;
                } else {
                  return date.format('ddd, MMM D h:mm A');
                }
              })()}
            </time>
          </div>
        </div>
        <MemoryWithTabs memory={memory} />
      </div>
    </div>
  );
}
