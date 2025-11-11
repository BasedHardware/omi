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
          <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400 md:text-base">
            <time dateTime={new Date(memory.created_at).toISOString()}>
              {moment(memory.created_at).format('MMMM Do YYYY, h:mm a')}
            </time>
          </div>
        </div>
        <MemoryWithTabs memory={memory} />
      </div>
    </div>
  );
}
