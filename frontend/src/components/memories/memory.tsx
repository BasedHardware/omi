import { Memory as MemoryType } from '@/src/types/memory.types';
import moment from 'moment';
import Summary from './sumary';
import Tabs from './tabs';
import Transcription from './transcript/transcription';

interface MemoryProps {
  memory: MemoryType;
  searchParams: any;
}

export default function Memory({ memory, searchParams }: MemoryProps) {
  const currentTab = searchParams.tab ?? 'sum';
  return (
    <div className="mx-auto my-12 max-w-screen-md rounded-2xl border border-solid border-zinc-800 py-12 text-white">
      <div className="px-12">
        <h2 className="text-3xl font-bold">{memory.structured.title}</h2>
        <p className="my-2 text-gray-500">
          {moment(memory.created_at).format('MMMM Do YYYY, h:mm:ss a')}
        </p>
        <span className="rounded-full bg-gray-700 px-3 py-1 text-sm">
          {memory.structured.emoji} {memory.structured.category}
        </span>
      </div>
      <Tabs currentTab={currentTab} />
      <div className="px-12">
        {currentTab === 'sum' ? (
          <Summary memory={memory} />
        ) : (
          <Transcription transcript={memory.transcript_segments} />
        )}
      </div>
    </div>
  );
}
