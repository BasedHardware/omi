'use client';

import { useSearchBox } from 'react-instantsearch';

interface TrendingItemProps {
  title: string;
  count: number;
  raking?: number;
}

export default function TrendingItem({ title, count, raking }: TrendingItemProps) {
  const { refine } = useSearchBox();

  const updateSearch = () => {
    refine(title);
  };

  return (
    <button
      onClick={updateSearch}
      className="fle-col flex w-full cursor-pointer flex-col px-5 py-4 transition-all hover:bg-zinc-800/50"
    >
      <div className="flex items-center gap-2">
        {raking && (
          <p
            className={`grid h-4 w-4 place-items-center rounded-full text-xs font-bold shadow-md md:text-xs ${
              raking === 1
                ? 'bg-yellow-400 text-black/60 shadow-yellow-600'
                : raking === 2
                ? 'bg-gray-400 text-black/60'
                : 'bg-gray-500 text-black/60'
            }`}
          >
            {raking}
          </p>
        )}
        <h3 className="text-sm md:text-base">{title}</h3>
      </div>
      <p className="text-xs text-neutral-400 md:text-sm">{count} memories</p>
    </button>
  );
}
