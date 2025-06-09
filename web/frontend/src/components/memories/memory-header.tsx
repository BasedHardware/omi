import { NavArrowLeft } from 'iconoir-react';
import Link from 'next/link';

export default function MemoryHeader() {
  return (
    <div className="mb-8">
      <Link
        href="/apps"
        className="group inline-flex items-center gap-2 rounded-full bg-zinc-800/50 px-4 py-2 text-sm text-zinc-400 ring-1 ring-inset ring-zinc-800 transition hover:bg-zinc-800 hover:text-zinc-300"
      >
        <NavArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
        Back to Apps
      </Link>
    </div>
  );
}
