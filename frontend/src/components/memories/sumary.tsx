import { Memory } from '@/src/types/memory.types';
import ActionItems from './action-items';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  return (
    <div className="flex flex-col gap-10">
      <div className="mt-10">
        <h3 className="text-2xl font-semibold">Overview</h3>
        <p className="mt-3 text-lg">{memory.structured.overview}</p>
      </div>
      <ActionItems items={memory.structured.action_items} />
    </div>
  );
}
