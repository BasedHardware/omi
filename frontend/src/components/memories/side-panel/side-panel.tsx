import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import moment from 'moment';
import MemoryWithTabs from '../summary/memory-with-tabs';

interface SidePanelProps {
  previewId: string | undefined;
}

export default async function SidePanel({ previewId }: SidePanelProps) {
  const memory = await getSharedMemory(previewId ?? '');

  if (!memory) {
    return (
      <div className="mx-auto px-12 py-12 text-white">
        <h1 className="font-semibolds text-xl">Memory not found</h1>
        <p className="mt-3 text-lg text-zinc-400">
          The memory you are looking for does not exist. Please check the URL and try
          again.
        </p>
      </div>
    );
  }

  return (
    <div data-vaul-no-drag className="">
      <div className="rounded-2xl text-white">
        <div className="overflow-hidden pb-6">
          <div className="relative z-50">
            <div className="px-4 md:px-12">
              <h2 className="select-text text-2xl font-bold md:text-3xl">
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
        </div>
      </div>
      <div className="absolute top-0 z-10 h-full w-full  select-none blur-3xl">
        <div className="absolute right-[0rem] top-[-70px] h-[10rem] w-[100%] bg-[#1758e74f] opacity-30" />
      </div>
    </div>
  );
}
