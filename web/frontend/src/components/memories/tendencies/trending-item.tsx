'use client';

import { Trend } from '@/src/types/trends/trends.types';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';
import { useSearchBox } from 'react-instantsearch';

interface TrendingItemProps {
  trend: Trend;
  index: number;
}

export default function TrendingItem({ trend, index }: TrendingItemProps) {
  const { refine } = useSearchBox();

  const updateSearch = () => {
    refine(trend.category);
  };

  return (
    <button
      onClick={updateSearch}
      className="fle-col flex w-full cursor-pointer flex-col px-5 py-4 transition-all hover:bg-zinc-800/50"
    >
      <div className="flex items-center gap-2">
        {/* <p
          className={`grid h-4 w-4 place-items-center rounded-full text-xs font-bold shadow-md md:text-xs ${
            index === 0
              ? 'bg-yellow-400 text-black/60 shadow-yellow-600'
              : index === 1
              ? 'bg-gray-400 text-black/60'
              : 'bg-gray-500 text-black/60'
          }`}
        >
          {index + 1}
        </p> */}
        <h3 className="text-sm md:text-base">{capitalizeFirstLetter(trend.category)}</h3>
      </div>
      <p className="text-xs text-neutral-400 md:text-sm">
        {trend.topics.map(
          (topic, index) =>
            ' ' +
            capitalizeFirstLetter(topic.topic) +
            (index === trend.topics.length - 1 ? '' : ', '),
        )}
      </p>
    </button>
  );
}
