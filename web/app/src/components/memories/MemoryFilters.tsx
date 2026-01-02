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
      return filterOptions.find(o => o.category === activeCategories[0])?.label || 'Filter';
    }
    return `${activeCategories.length} selected`;
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg',
          'bg-bg-tertiary border border-bg-quaternary',
          'text-sm text-text-secondary hover:text-text-primary',
          'transition-colors',
          activeCategories.length > 0 && 'border-purple-primary/30 text-purple-primary'
        )}
      >
        <Filter className="w-4 h-4" />
        <span>{getButtonLabel()}</span>
        <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 top-full mt-1 z-20 bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg py-1 min-w-[160px]">
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
                    'w-full flex items-center gap-2 px-3 py-2 text-sm',
                    'hover:bg-bg-tertiary transition-colors text-left',
                    isActive ? 'text-purple-primary' : 'text-text-secondary'
                  )}
                >
                  {option.icon}
                  <span className="flex-1">{option.label}</span>
                  {isActive && <Check className="w-4 h-4" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
