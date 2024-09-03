import { Memory } from '@/src/types/memory.types';
import Link from 'next/link';

interface MemoryItemProps {
  memory: Memory;
}

export default function MemoryItem({ memory }: MemoryItemProps) {
  return (
    <Link key={memory.id} className="mb-4" href={`/memories?previewId=${memory.id}`} scroll={false}>
      <div className="text-2xl font-bold">
        {!memory?.structured?.title ? 'Untitle memory' : memory.structured.title}
      </div>
      <div className="line-clamp-3 text-base font-extralight">
        {!memory?.structured?.overview
          ? "This memory doesn't have an overview"
          : memory?.structured?.overview}
      </div>
    </Link>
  );
}
