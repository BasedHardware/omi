'use client';

import { getCategoryMetadata } from '../../utils/category';

interface CategoryHeaderProps {
  category: string;
  totalApps: number;
}

export function CategoryHeader({ category, totalApps }: CategoryHeaderProps) {
  const metadata = getCategoryMetadata(category);
  const Icon = metadata.icon;

  return (
    <div>
      <div className="flex items-start space-x-4">
        <div className={`rounded-xl p-3 ${metadata.theme.accent}`}>
          <Icon className={`h-8 w-8 ${metadata.theme.primary}`} />
        </div>
        <div className="flex-1">
          <h1 className="flex items-center text-3xl font-bold text-white">
            {metadata.displayName}
            <span className="ml-3 text-base font-normal text-gray-400">
              ({totalApps})
            </span>
          </h1>
          <p className="mt-2 text-gray-400">{metadata.description}</p>
        </div>
      </div>
    </div>
  );
}
