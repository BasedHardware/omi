import getSharedMemory from '@/src/actions/memories/get-shared-memory';

interface SidePanelProps {
  previewId: string | undefined;
}

export default async function SidePanel({ previewId }: SidePanelProps) {
  const memory = await getSharedMemory(previewId ?? '');
  return (
    <div>
      {JSON.stringify(memory)}
    </div>
  );
}
