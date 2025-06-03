import { Memory as MemoryType } from '@/src/types/memory.types';
import moment from 'moment';
import { SearchParamsTypes } from '@/src/types/params.types';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import MemoryWithTabs from './summary/memory-with-tabs';

interface MemoryProps {
  memory: MemoryType;
  searchParams: SearchParamsTypes;
}

export default function Memory({ memory, searchParams }: MemoryProps) {
  const currentTab = searchParams.tab ?? 'sum';
  return (
    <div className="relative overflow-hidden rounded-2xl border border-zinc-800/50 bg-zinc-900/50 pb-6 text-white shadow-xl backdrop-blur-lg md:pb-12">
      <div className="relative py-6 md:pt-12">
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-zinc-900/20 to-zinc-900/40" />
        
        {/* Content */}
        <div className="relative z-10">
          <div className="px-6 md:px-12">
            <div className="flex flex-col gap-3">
              <h2 className="text-2xl font-bold tracking-tight md:text-3xl">
                {memory.structured.title || DEFAULT_TITLE_MEMORY}
              </h2>
              <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400 md:text-base">
                <time dateTime={new Date(memory.created_at).toISOString()}>
                  {moment(memory.created_at).format('MMMM Do YYYY, h:mm:ss a')}
                </time>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-800 px-3 py-1 text-xs font-medium text-zinc-300 ring-1 ring-inset ring-zinc-800/50 md:text-sm">
                  {memory.structured.emoji}{' '}
                  {memory.structured.category.charAt(0).toUpperCase() +
                    memory.structured.category.slice(1)}
                </span>
              </div>
            </div>
          </div>
          <MemoryWithTabs memory={memory} />
        </div>

        {/* Background decorative elements */}
        <div className="absolute left-1/2 top-0 -z-10 h-[800px] w-[800px] -translate-x-1/2 -translate-y-1/2 opacity-20">
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-purple-500 blur-3xl" />
        </div>
      </div>
    </div>
  );
}
