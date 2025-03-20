/* eslint-disable prettier/prettier */
'use client';

import Link from 'next/link';
import { useRef, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { categoryMetadata, type CategoryMetadata } from '../../utils/category';

interface ScrollableCategoryNavProps {
  currentCategory: string;
}

export function ScrollableCategoryNav({ currentCategory }: ScrollableCategoryNavProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const categories = Object.values(categoryMetadata);

  // Scroll to active category on mount
  useEffect(() => {
    const container = scrollContainerRef.current;
    const activeItem = container?.querySelector('[data-active="true"]');
    
    if (container && activeItem) {
      const containerWidth = container.offsetWidth;
      const itemLeft = (activeItem as HTMLElement).offsetLeft;
      const itemWidth = (activeItem as HTMLElement).offsetWidth;
      
      // Center the active item
      container.scrollLeft = itemLeft - containerWidth / 2 + itemWidth / 2;
    }
  }, [currentCategory]);

  const scroll = (direction: 'left' | 'right') => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const scrollAmount = container.offsetWidth * 0.8;
    const targetScroll = container.scrollLeft + (direction === 'left' ? -scrollAmount : scrollAmount);
    
    container.scrollTo({
      left: targetScroll,
      behavior: 'smooth'
    });
  };

  return (
    <div className="relative">
      {/* Left scroll button */}
      <button
        onClick={() => scroll('left')}
        className="absolute -left-4 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-[#1A1F2E] text-gray-400 shadow-lg transition-colors hover:text-white"
      >
        <ChevronLeft className="h-5 w-5" />
      </button>

      {/* Scrollable container */}
      <div
        ref={scrollContainerRef}
        className="no-scrollbar flex items-center space-x-2 overflow-x-auto scroll-smooth px-4"
      >
        {categories.map((category) => (
          <Link
            key={category.id}
            href={`/apps/category/${category.id}`}
            data-active={currentCategory === category.id}
            className={`
              flex items-center space-x-2 rounded-full px-4 py-2 transition-all
              ${
                currentCategory === category.id
                  ? `${category.theme.accent} ${category.theme.primary}`
                  : 'text-gray-400 hover:bg-white/5 hover:text-white'
              }
            `}
          >
            <category.icon className="h-4 w-4" />
            <span className="whitespace-nowrap text-sm font-medium">
              {category.displayName}
            </span>
          </Link>
        ))}
      </div>

      {/* Right scroll button */}
      <button
        onClick={() => scroll('right')}
        className="absolute -right-4 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-[#1A1F2E] text-gray-400 shadow-lg transition-colors hover:text-white"
      >
        <ChevronRight className="h-5 w-5" />
      </button>
    </div>
  );
} 