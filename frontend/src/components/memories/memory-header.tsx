import { NavArrowLeft } from 'iconoir-react';
import Link from 'next/link';

export default function MemoryHeader() {
  return (
    <div className="mb-4">
      <Link
        href="/memories"
        className="block flex w-fit items-center gap-1.5 rounded-md px-3.5 py-2 text-white transition-colors hover:bg-zinc-800"
      >
        <NavArrowLeft className="-ml-1.5 inline-block text-sm" />
        Back to Memories
      </Link>
    </div>
  );
}
