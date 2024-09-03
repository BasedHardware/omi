import getPublicMemories from '@/src/actions/memories/get-public-memories';
import MemoryItem from './memory-item';

export default async function MemoryList({ searchParams }) {
  const memories = await getPublicMemories();
  return (
    <div className="mt-20 text-white">
      <div className="flex flex-col gap-10">
        {memories.map((memory) => (
          <MemoryItem key={memory.id} memory={memory} searchParams={searchParams} />
        ))}
      </div>
    </div>
  );
}
