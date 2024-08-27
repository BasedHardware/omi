import getMemory from '@/src/actions/memories/get-memory';
import Memory from '@/src/components/memories/memory';

export default async function MemoryPage({ params }) {
  const memoryId = params.id;
  const memory = await getMemory(memoryId);
  return (
    <div>
      <Memory memory={memory} />
    </div>
  );
}
