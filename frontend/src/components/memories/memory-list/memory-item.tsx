import { Memory } from '@/src/types/memory.types';
import moment from 'moment';
import Link from 'next/link';

interface MemoryItemProps {
  memory: Memory;
}

export default function MemoryItem({ memory }: MemoryItemProps) {
  return (
    <Link key={memory.id} className="mb-4 border-b border-solid border-gray-700 pb-8 w-full flex gap-4 md:gap-7 items-start" href={`/memories?previewId=${memory.id}`}>
        <div className='p-2.5 md:p-4 rounded-md bg-zinc-800 w-fith-fit md:text-base text-sm'>
          11
        </div>
      <div className='w-full'>
        <h2 className="text-base md:text-xl font-semibold">
          {!memory?.structured?.title ? 'Untitle memory' : memory.structured.title}
        </h2>
        <div className="line-clamp-2 text-sm md:text-base font-extralight text-zinc-300">
          {!memory?.structured?.overview
            ? "This memory doesn't have an overview"
            : memory?.structured?.overview}
        </div>
        <div className='mt-8 flex justify-between'>
          <p className="rounded-full text-sm">
            {memory.structured.emoji}{' '}
            {memory.structured.category.charAt(0).toUpperCase() +
              memory.structured.category.slice(1)}
          </p>
          <p className='text-sm'>
            {moment(memory.created_at).format('MMMM Do YYYY')}
          </p>
        </div>
      </div>
    </Link>
  );
}
