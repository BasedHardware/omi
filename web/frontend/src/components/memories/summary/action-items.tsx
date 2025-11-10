import { ActionItems as ActionItemsType } from '@/src/types/memory.types';
import { CheckCircle } from 'iconoir-react';

interface ActionsItemsProps {
  items: ActionItemsType[];
}

export default function ActionItems({ items }: ActionsItemsProps) {
  return (
    <div>
      <h3 className="mb-4 text-xl font-semibold text-white md:text-2xl">Action Items</h3>
      <ul className="space-y-4 text-base md:text-lg">
        {items.map((item, index) => (
          <li key={index} className="flex items-start gap-3">
            {item.completed ? (
              <div className="mt-0.5">
                <CheckCircle className="h-5 w-5 text-green-400" />
              </div>
            ) : (
              <div className="mt-0.5">
                <CheckCircle className="h-5 w-5 text-zinc-600" />
              </div>
            )}
            <p className="flex-1 leading-relaxed text-zinc-300">{item.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
