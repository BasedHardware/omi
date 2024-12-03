'use client';

import { getCategoryDisplay } from '../../utils/category';

export interface CategoryNavProps {
  categories: {
    name: string;
    count: number;
  }[];
}

export function CategoryNav({ categories }: CategoryNavProps) {
  return (
    <div className="mb-12 overflow-x-auto">
      <div className="flex flex-wrap gap-2">
        {categories.map(({ name, count }) => (
          <a
            key={name}
            href={`#${name}`}
            className="flex items-center gap-2 rounded-full bg-gray-800/50 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-700/50 hover:text-white"
          >
            <span>{getCategoryDisplay(name)}</span>
            <span className="rounded-full bg-gray-700/50 px-2 py-0.5 text-xs">
              {count}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
