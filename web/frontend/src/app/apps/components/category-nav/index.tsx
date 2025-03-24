'use client';

import { useState, useCallback } from 'react';
import { getCategoryDisplay, getCategoryIcon } from '../../utils/category';
import { ChevronDown, Grid } from 'lucide-react';
import { useClickOutside } from '../../hooks/useClickOutside';

export interface CategoryNavProps {
  categories: {
    name: string;
    count: number;
  }[];
}

const PRIMARY_CATEGORIES = [
  'productivity-and-organization',
  'other',
  'personality-emulation',
  'education-and-learning',
];

export function CategoryNav({ categories }: CategoryNavProps) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const handleClose = useCallback(() => {
    setIsDropdownOpen(false);
  }, []);

  const dropdownRef = useClickOutside(handleClose);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setIsDropdownOpen(false);
    }
  };

  const primaryCategories = categories.filter((cat) =>
    PRIMARY_CATEGORIES.includes(cat.name),
  );

  const secondaryCategories = categories.filter(
    (cat) => !PRIMARY_CATEGORIES.includes(cat.name),
  );

  const handleCategorySelect = (categoryName: string) => {
    setSelectedCategory(categoryName);
    setIsDropdownOpen(false);
    const element = document.getElementById(categoryName);
    element?.scrollIntoView({ behavior: 'smooth' });
  };

  const allCategories = [...primaryCategories, ...secondaryCategories];
  const currentCategory = selectedCategory
    ? allCategories.find((cat) => cat.name === selectedCategory)
    : allCategories[0];

  return (
    <>
      {/* Desktop View */}
      <div className="hidden md:block">
        <div className="flex flex-wrap items-center gap-2">
          {primaryCategories.map(({ name, count }) => {
            const Icon = getCategoryIcon(name);
            return (
              <a
                key={name}
                href={`#${name}`}
                className="flex items-center gap-2 rounded-lg bg-[#1A1F2E] px-4 py-2.5 text-sm font-medium text-white transition-all duration-300 hover:bg-[#242938] hover:shadow-lg"
              >
                <Icon className="h-4 w-4 flex-shrink-0 text-[#6C8EEF]" />
                <span>{getCategoryDisplay(name)}</span>
                <span className="rounded-full bg-[#2A3142] px-2 py-0.5 text-xs">
                  {count}
                </span>
              </a>
            );
          })}

          <div ref={dropdownRef} className="relative">
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              onKeyDown={handleKeyDown}
              className="flex items-center gap-2 rounded-lg bg-[#1A1F2E] px-4 py-2.5 text-sm font-medium text-white transition-all duration-300 hover:bg-[#242938] hover:shadow-lg"
              aria-expanded={isDropdownOpen}
              aria-haspopup="true"
            >
              <Grid className="h-4 w-4 flex-shrink-0 text-[#6C8EEF]" />
              <span>More Categories</span>
              <ChevronDown
                className={`h-4 w-4 transition-transform duration-300 ${
                  isDropdownOpen ? 'rotate-180' : ''
                }`}
                aria-hidden="true"
              />
            </button>

            {isDropdownOpen && (
              <div
                className="absolute right-0 z-50 mt-2 w-64 rounded-xl bg-[#1A1F2E] p-2 shadow-xl ring-1 ring-black ring-opacity-5 focus:outline-none"
                role="menu"
                aria-orientation="vertical"
                tabIndex={-1}
              >
                {secondaryCategories.map(({ name, count }) => {
                  const Icon = getCategoryIcon(name);
                  return (
                    <a
                      key={name}
                      href={`#${name}`}
                      onClick={() => setIsDropdownOpen(false)}
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-gray-300 transition-colors hover:bg-[#242938] hover:text-white"
                      role="menuitem"
                    >
                      <Icon className="h-4 w-4 flex-shrink-0 text-[#6C8EEF]" />
                      <span className="flex-1">{getCategoryDisplay(name)}</span>
                      <span className="rounded-full bg-[#2A3142] px-2 py-0.5 text-xs">
                        {count}
                      </span>
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile View */}
      <div className="block md:hidden">
        <div ref={dropdownRef} className="relative w-full">
          <button
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            onKeyDown={handleKeyDown}
            className="flex w-full items-center justify-between gap-2 rounded-lg bg-[#1A1F2E] px-4 py-3 text-sm font-medium text-white transition-all duration-300 hover:bg-[#242938] hover:shadow-lg"
            aria-expanded={isDropdownOpen}
            aria-haspopup="true"
          >
            <div className="flex items-center gap-2">
              {currentCategory && (
                <>
                  {(() => {
                    const Icon = getCategoryIcon(currentCategory.name);
                    return <Icon className="h-4 w-4 flex-shrink-0 text-[#6C8EEF]" />;
                  })()}
                  <span>{getCategoryDisplay(currentCategory.name)}</span>
                  <span className="rounded-full bg-[#2A3142] px-2 py-0.5 text-xs">
                    {currentCategory.count}
                  </span>
                </>
              )}
            </div>
            <ChevronDown
              className={`h-4 w-4 transition-transform duration-300 ${
                isDropdownOpen ? 'rotate-180' : ''
              }`}
              aria-hidden="true"
            />
          </button>

          {isDropdownOpen && (
            <div
              className="absolute left-0 right-0 z-50 mt-2 rounded-xl bg-[#1A1F2E] p-2 shadow-xl ring-1 ring-black ring-opacity-5 focus:outline-none"
              role="menu"
              aria-orientation="vertical"
              tabIndex={-1}
            >
              {allCategories.map(({ name, count }) => {
                const Icon = getCategoryIcon(name);
                return (
                  <button
                    key={name}
                    onClick={() => handleCategorySelect(name)}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sm text-gray-300 transition-colors hover:bg-[#242938] hover:text-white"
                    role="menuitem"
                  >
                    <Icon className="h-4 w-4 flex-shrink-0 text-[#6C8EEF]" />
                    <span className="flex-1 text-left">{getCategoryDisplay(name)}</span>
                    <span className="rounded-full bg-[#2A3142] px-2 py-0.5 text-xs">
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
