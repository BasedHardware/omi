import { ActionItems as ActionItemsType } from '@/src/types/memory.types';
import { CheckCircle } from 'iconoir-react';

interface ActionsItemsProps {
  items: ActionItemsType[];
}

export default function ActionItems({ items }: ActionsItemsProps) {
  return (
    <div className="px-4 md:px-12">
      <h3 className="text-xl font-semibold md:text-2xl">Action Items</h3>
      <ul className="mt-3 text-base md:text-lg">
        {items.map((item, index) => (
          <li key={index} className="my-5 flex items-start gap-3 first:mt-0">
            {item.completed ? (
              <div className="mt-1">
                <CheckCircle className="min-w-min text-sm text-green-400" />
              </div>
            ) : (
              <div className="mt-1">
                <CheckCircle className="min-w-min text-sm text-zinc-600" />
              </div>
            )}
            <p>{item.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
