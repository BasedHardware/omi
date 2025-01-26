/* eslint-disable prettier/prettier */
'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { getCategoryIcon, getCategoryMetadata } from '../../utils/category';

interface CategoryBreadcrumbProps {
  category: string;
}

export function CategoryBreadcrumb({ category }: CategoryBreadcrumbProps) {
  const metadata = getCategoryMetadata(category);
  const Icon = getCategoryIcon(category);

  return (
    <nav className="flex items-center space-x-2 text-sm text-gray-400">
      <Link
        href="/apps"
        className="flex items-center text-[#6C8EEF] transition-colors hover:text-[#5A7DE8]"
      >
        Apps
      </Link>
      <ChevronRight className="h-4 w-4" />
      <div className="flex items-center">
        <Icon className="mr-1.5 h-4 w-4" />
        <span className={metadata.theme.secondary}>{metadata.displayName}</span>
      </div>
    </nav>
  );
} 