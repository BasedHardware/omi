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
    <div className="relative rounded-2xl border border-solid border-zinc-800 bg-transparent pb-6 text-white shadow-md shadow-gray-900 backdrop-blur-lg md:mx-auto md:pb-12">
      <div className="relative overflow-hidden py-6 md:pt-12">
        <div className="relative z-50">
          <div className="px-4 md:px-12">
            <h2 className="text-2xl font-bold md:text-3xl">
              {memory.structured.title || DEFAULT_TITLE_MEMORY}
            </h2>
            <p className="my-2 text-sm text-gray-500 md:text-base">
              {moment(memory.created_at).format('MMMM Do YYYY, h:mm:ss a')}
            </p>
            <span className="rounded-full bg-gray-700 px-3 py-1.5 text-xs md:text-sm">
              {memory.structured.emoji}{' '}
              {memory.structured.category.charAt(0).toUpperCase() +
                memory.structured.category.slice(1)}
            </span>
          </div>
          <MemoryWithTabs memory={memory} />
        </div>
        <div className="absolute top-0 z-10 h-full w-full  select-none blur-3xl">
          <div className="absolute right-[0rem] top-[-70px] h-[10rem] w-[100%] bg-[#1758e74f] opacity-30" />
        </div>
      </div>
    </div>
  );
}
