import getMemory from '@/src/actions/memories/get-memory';
import Memory from '@/src/components/memories/memory';

export default async function MemoryPage({ params, searchParams }) {
  const memoryId = params.id;
  const memory = await getMemory(memoryId);
  return (
    <div>
      <Memory memory={memory} searchParams={searchParams} />
    </div>
  );
}
