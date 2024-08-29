import { Memory as MemoryType } from '@/src/types/memory.types';
import moment from 'moment';
import Summary from './sumary';
import Tabs from './tabs';
import Transcription from './transcript/transcription';
import { SearchParamsTypes } from '@/src/types/params.types';

interface MemoryProps {
  memory: MemoryType;
  searchParams: SearchParamsTypes;
}

export default function Memory({ memory, searchParams }: MemoryProps) {
  const currentTab = searchParams.tab ?? 'sum';
  return (
    <div className="mx-3 my-10 max-w-screen-md rounded-2xl border border-solid border-zinc-800 py-6 text-white md:mx-auto md:my-28 md:py-12">
      <div className="px-4 md:px-12">
        <h2 className="line-clamp-2 text-2xl font-bold md:text-3xl">
          {memory.structured.title}
        </h2>
        <p className="my-2 text-sm text-gray-500 md:text-base">
          {moment(memory.created_at).format('MMMM Do YYYY, h:mm:ss a')}
        </p>
        <span className="rounded-full bg-gray-700 px-3 py-1.5 text-xs md:text-sm">
          {memory.structured.emoji} {memory.structured.category}
        </span>
      </div>
      <Tabs currentTab={currentTab} />
      <div className="px-4 md:px-12">
        {currentTab === 'sum' ? (
          <Summary memory={memory} />
        ) : (
          <Transcription transcript={memory.transcript_segments} />
        )}
      </div>
    </div>
  );
}
