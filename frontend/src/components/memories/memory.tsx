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
    <div className="relative mx-3 my-10 max-w-screen-md overflow-hidden rounded-2xl border border-solid border-zinc-800 bg-transparent py-6 text-white shadow-md shadow-gray-900 backdrop-blur-lg md:mx-auto md:my-28 md:py-12">
      <div className="relative z-50">
        <div className="px-4 md:px-12">
          <h2 className="text-2xl font-bold md:text-3xl">{memory.structured.title}</h2>
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
            <Transcription
              transcript={memory.transcript_segments}
              externalData={memory.external_data}
            />
          )}
        </div>
      </div>
      <div className="absolute top-0 z-10 h-full w-full  select-none blur-3xl">
        <div className="absolute right-[0rem] top-[-70px] h-[10rem] w-[100%] bg-[#1758e74f] opacity-30" />
      </div>
    </div>
  );
}
