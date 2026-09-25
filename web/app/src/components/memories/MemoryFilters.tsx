'use client';

import { useState } from 'react';
import { Lightbulb, FileText, Settings, Filter, ChevronDown, Check } from 'lucide-react';
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
    icon: <Lightbulb className="h-3.5 w-3.5" />,
  },
  {
    category: 'manual',
    label: 'Manual',
    icon: <FileText className="h-3.5 w-3.5" />,
  },
  {
    category: 'system',
    label: 'System',
    icon: <Settings className="h-3.5 w-3.5" />,
  },
];

export function MemoryFilters({
  activeCategories,
  onCategoriesChange,
}: MemoryFiltersProps) {
  const [isOpen, setIsOpen] = useState(false);
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

  // Get label for button
  const getButtonLabel = () => {
    if (isAllSelected) return 'All';
    if (activeCategories.length === 1) {
      return (
        filterOptions.find((o) => o.category === activeCategories[0])?.label || 'Filter'
      );
    }
    return `${activeCategories.length} selected`;
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 rounded-lg px-3 py-2',
          'border border-bg-quaternary bg-bg-tertiary',
          'text-sm text-text-secondary hover:text-text-primary',
          'transition-colors',
          activeCategories.length > 0 && 'border-white/30 text-white',
        )}
      >
        <Filter className="h-4 w-4" />
        <span>{getButtonLabel()}</span>
        <ChevronDown
          className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')}
        />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full z-50 mt-1 min-w-[160px] rounded-lg border border-bg-tertiary bg-bg-secondary py-1 shadow-lg">
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
                    'flex w-full items-center gap-2 px-3 py-2 text-sm',
                    'text-left transition-colors hover:bg-bg-tertiary',
                    isActive ? 'text-white' : 'text-text-secondary',
                  )}
                >
                  {option.icon}
                  <span className="flex-1">{option.label}</span>
                  {isActive && <Check className="h-4 w-4" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
