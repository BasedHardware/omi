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
      className="group flex w-full items-start gap-4 border-b border-solid border-gray-700 pb-8 last:border-transparent md:gap-7"
      href={`/memories?${_searchParams.toString()}&previewId=${memory.id}`}
    >
      <div className="w-fith-fit rounded-md bg-zinc-800 p-2.5 text-sm transition-colors group-hover:bg-zinc-700 md:p-4 md:text-base">
        {memory.structured.emoji}
      </div>
      <div className="w-full">
        <h2 className="line-clamp-2 text-base font-semibold group-hover:underline md:text-xl">
          {!memory?.structured?.title ? 'Untitle memory' : memory.structured.title}
        </h2>
        <div className="line-clamp-2 text-sm font-extralight text-zinc-300 md:text-base">
          {!memory?.structured?.overview
            ? "This memory doesn't have an overview"
            : memory?.structured?.overview}
        </div>
        <div className="mt-8 flex items-center justify-start gap-1.5 text-xs text-zinc-400 md:text-sm">
          <p className="">{moment(memory.created_at).format('MMM Do YYYY')}</p>
          <div className="text-xs">•</div>
          <p className="rounded-full">
            {memory.structured.category.charAt(0).toUpperCase() +
              memory.structured.category.slice(1)}
          </p>
        </div>
      </div>
    </Link>
  );
}
