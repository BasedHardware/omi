'use client';

import { getCategoryDisplay } from '../../utils/category';

interface CategoryHeaderProps {
  category: string;
  pluginCount: number;
}

export function CategoryHeader({ category, pluginCount }: CategoryHeaderProps) {
  return (
    <h2 className="mb-6 text-2xl font-bold text-white">
      {getCategoryDisplay(category)}
      <span className="ml-2 text-sm font-normal text-gray-400">({pluginCount})</span>
    </h2>
  );
}
