import { Memory } from '@/src/types/memory.types';
import moment from 'moment';
import Link from 'next/link';

interface MemoryItemProps {
  memory: Memory;
}

export default function MemoryItem({ memory, searchParams }: MemoryItemProps) {
  const _searchParams = new URLSearchParams(searchParams);
  return (
    <Link
      className="mb-4 flex w-full items-start gap-4 border-b border-solid border-gray-700 pb-8 md:gap-7"
      href={`/memories?${_searchParams.toString()}&previewId=${memory.id}`}
    >
      <div className="w-fith-fit rounded-md bg-zinc-800 p-2.5 text-sm md:p-4 md:text-base">
        11
      </div>
      <div className="w-full">
        <h2 className="text-base font-semibold md:text-xl">
          {!memory?.structured?.title ? 'Untitle memory' : memory.structured.title}
        </h2>
        <div className="line-clamp-2 text-sm font-extralight text-zinc-300 md:text-base">
          {!memory?.structured?.overview
            ? "This memory doesn't have an overview"
            : memory?.structured?.overview}
        </div>
        <div className="mt-8 flex justify-between">
          <p className="rounded-full text-sm">
            {memory.structured.emoji}{' '}
            {memory.structured.category.charAt(0).toUpperCase() +
              memory.structured.category.slice(1)}
          </p>
          <p className="text-sm">{moment(memory.created_at).format('MMMM Do YYYY')}</p>
        </div>
      </div>
    </Link>
  );
}
