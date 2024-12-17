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
    <div className="flex items-center gap-2 sm:gap-4">
      <div className={`rounded-lg p-2 sm:rounded-xl sm:p-3 ${metadata.theme.accent}`}>
        <Icon className={`h-5 w-5 sm:h-8 sm:w-8 ${metadata.theme.primary}`} />
      </div>
      <div className="min-w-0 flex-1">
        <h1 className="flex items-center gap-2 text-xl font-bold text-white sm:text-2xl md:text-3xl">
          {metadata.displayName}
          <span className="inline-flex items-center rounded-full bg-white/5 px-2 py-0.5 text-sm text-gray-400 sm:text-base">
            {totalApps}
          </span>
        </h1>
        <p className="mt-0.5 line-clamp-1 text-sm text-gray-400 sm:mt-2 sm:line-clamp-none sm:text-base">
          {metadata.description}
        </p>
      </div>
    </div>
  );
}
