'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Star, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AppCategory, AppCapability, AppsFilters, SortOption } from '@/types/apps';

interface FilterSheetProps {
  open: boolean;
  onClose: () => void;
  filters: AppsFilters;
  onFiltersChange: (filters: AppsFilters) => void;
  categories: AppCategory[];
  capabilities: AppCapability[];
}

const RATING_OPTIONS = [
  { value: 4, label: '4+ Stars' },
  { value: 3, label: '3+ Stars' },
  { value: 2, label: '2+ Stars' },
  { value: 1, label: '1+ Stars' },
];

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'installs_desc', label: 'Most Installs' },
  { value: 'rating_desc', label: 'Highest Rated' },
  { value: 'rating_asc', label: 'Lowest Rated' },
  { value: 'name_asc', label: 'A-Z' },
  { value: 'name_desc', label: 'Z-A' },
];

export function FilterSheet({
  open,
  onClose,
  filters,
  onFiltersChange,
  categories,
  capabilities,
}: FilterSheetProps) {
  const [localFilters, setLocalFilters] = useState<AppsFilters>(filters);

  // Sync with external filters when sheet opens
  useEffect(() => {
    if (open) {
      setLocalFilters(filters);
    }
  }, [open, filters]);

  const handleApply = () => {
    onFiltersChange(localFilters);
    onClose();
  };

  const handleReset = () => {
    setLocalFilters({});
  };

  const toggleCategory = (categoryId: string) => {
    setLocalFilters(prev => ({
      ...prev,
      category: prev.category === categoryId ? undefined : categoryId,
    }));
  };

  const toggleCapability = (capabilityId: string) => {
    setLocalFilters(prev => ({
      ...prev,
      capability: prev.capability === capabilityId ? undefined : capabilityId,
    }));
  };

  const toggleRating = (rating: number) => {
    setLocalFilters(prev => ({
      ...prev,
      rating: prev.rating === rating ? undefined : rating,
    }));
  };

  const toggleSort = (sort: SortOption) => {
    setLocalFilters(prev => ({
      ...prev,
      sort: prev.sort === sort ? undefined : sort,
    }));
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-40"
            onClick={onClose}
          />

          {/* Sheet */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'fixed top-0 right-0 bottom-0 z-50',
              'w-full sm:w-[400px] max-w-full',
              'bg-bg-secondary border-l border-bg-tertiary',
              'flex flex-col',
              'shadow-2xl'
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-bg-tertiary">
              <h2 className="text-lg font-semibold text-text-primary">Filters</h2>
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-5 h-5 text-text-secondary" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
              {/* Categories */}
              <FilterSection title="Category">
                <div className="flex flex-wrap gap-2">
                  {categories.map(category => (
                    <FilterChip
                      key={category.id}
                      label={category.title}
                      selected={localFilters.category === category.id}
                      onClick={() => toggleCategory(category.id)}
                    />
                  ))}
                </div>
              </FilterSection>

              {/* Capabilities */}
              <FilterSection title="Capability">
                <div className="flex flex-wrap gap-2">
                  {capabilities.map(capability => (
                    <FilterChip
                      key={capability.id}
                      label={capability.title}
                      selected={localFilters.capability === capability.id}
                      onClick={() => toggleCapability(capability.id)}
                    />
                  ))}
                </div>
              </FilterSection>

              {/* Rating */}
              <FilterSection title="Minimum Rating">
                <div className="flex flex-wrap gap-2">
                  {RATING_OPTIONS.map(option => (
                    <FilterChip
                      key={option.value}
                      label={option.label}
                      icon={<Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />}
                      selected={localFilters.rating === option.value}
                      onClick={() => toggleRating(option.value)}
                    />
                  ))}
                </div>
              </FilterSection>

              {/* Sort */}
              <FilterSection title="Sort By">
                <div className="flex flex-wrap gap-2">
                  {SORT_OPTIONS.map(option => (
                    <FilterChip
                      key={option.value}
                      label={option.label}
                      selected={localFilters.sort === option.value}
                      onClick={() => toggleSort(option.value)}
                    />
                  ))}
                </div>
              </FilterSection>
            </div>

            {/* Footer */}
            <div className="flex gap-3 p-4 border-t border-bg-tertiary">
              <button
                onClick={handleReset}
                className={cn(
                  'flex-1 px-4 py-2.5 rounded-xl',
                  'border border-bg-quaternary',
                  'text-text-secondary hover:bg-bg-tertiary',
                  'transition-colors'
                )}
              >
                Reset
              </button>
              <button
                onClick={handleApply}
                className={cn(
                  'flex-1 px-4 py-2.5 rounded-xl',
                  'bg-purple-primary text-white',
                  'hover:bg-purple-secondary',
                  'transition-colors'
                )}
              >
                Apply Filters
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-text-secondary mb-3">{title}</h3>
      {children}
    </div>
  );
}

interface FilterChipProps {
  label: string;
  icon?: React.ReactNode;
  selected: boolean;
  onClick: () => void;
}

function FilterChip({ label, icon, selected, onClick }: FilterChipProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 rounded-lg text-sm',
        'flex items-center gap-1.5',
        'transition-colors',
        selected
          ? 'bg-purple-primary text-white'
          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary'
      )}
    >
      {icon}
      {label}
      {selected && <Check className="w-3 h-3" />}
    </button>
  );
}
