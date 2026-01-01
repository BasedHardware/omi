'use client';

import { Lightbulb, FileText, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MemoryCategory } from '@/types/conversation';

interface MemoryFiltersProps {
  activeCategories: MemoryCategory[];
  onCategoriesChange: (categories: MemoryCategory[]) => void;
}

interface FilterOption {
  category: MemoryCategory | 'all';
  label: string;
  icon: React.ReactNode;
}

const filterOptions: FilterOption[] = [
  { category: 'all', label: 'All', icon: null },
  {
    category: 'interesting',
    label: 'Interesting',
    icon: <Lightbulb className="w-3.5 h-3.5" />,
  },
  {
    category: 'manual',
    label: 'Manual',
    icon: <FileText className="w-3.5 h-3.5" />,
  },
  {
    category: 'system',
    label: 'System',
    icon: <Settings className="w-3.5 h-3.5" />,
  },
];

export function MemoryFilters({ activeCategories, onCategoriesChange }: MemoryFiltersProps) {
  const isAllSelected = activeCategories.length === 0;

  const handleFilterClick = (category: MemoryCategory | 'all') => {
    if (category === 'all') {
      onCategoriesChange([]);
      return;
    }

    if (activeCategories.includes(category)) {
      // Remove category
      const newCategories = activeCategories.filter((c) => c !== category);
      onCategoriesChange(newCategories);
    } else {
      // Add category
      onCategoriesChange([...activeCategories, category]);
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-sm text-text-tertiary mr-1">Filter:</span>
      {filterOptions.map((option) => {
        const isActive =
          option.category === 'all'
            ? isAllSelected
            : activeCategories.includes(option.category as MemoryCategory);

        return (
          <button
            key={option.category}
            onClick={() => handleFilterClick(option.category)}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
              'transition-all duration-150',
              'border',
              isActive
                ? 'bg-purple-primary/10 border-purple-primary/30 text-purple-primary'
                : 'bg-bg-tertiary border-bg-quaternary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary'
            )}
          >
            {option.icon}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
