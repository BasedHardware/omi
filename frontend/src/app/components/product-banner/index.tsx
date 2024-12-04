'use client';

import { useState } from 'react';
import Image from 'next/image';
import { PRODUCT_INFO } from './types';
import { cn } from '@/src/lib/utils';

interface ProductBannerProps {
  variant?: 'detail' | 'floating' | 'category';
  className?: string;
  appName?: string;
  category?: string;
}

export function ProductBanner({
  variant = 'detail',
  className,
  appName,
  category,
}: ProductBannerProps) {
  const [isHovered, setIsHovered] = useState(false);

  const renderContent = () => {
    switch (variant) {
      case 'detail':
        return (
          <div className="relative overflow-hidden rounded-2xl bg-[#1A1F2E] p-4 shadow-lg sm:p-6">
            <div className="absolute inset-0 bg-gradient-to-r from-[#1A1F2E]/80 to-transparent" />
            <div className="relative z-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
              <div className="flex items-center gap-4 sm:gap-8">
                <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-xl sm:h-32 sm:w-32">
                  <Image
                    src={
                      isHovered
                        ? PRODUCT_INFO.images.secondary
                        : PRODUCT_INFO.images.primary
                    }
                    alt={PRODUCT_INFO.name}
                    fill
                    className="object-cover transition-transform duration-700 hover:scale-110"
                  />
                </div>
                <div className="min-w-0 space-y-2">
                  <h3 className="truncate text-xl font-bold text-white sm:text-2xl">
                    Experience {appName} with {PRODUCT_INFO.name}
                  </h3>
                  <p className="text-base text-gray-400 sm:text-lg">
                    AI-Powered Voice Assistant - {PRODUCT_INFO.shipping}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 sm:flex-col sm:items-end sm:gap-2">
                <span className="text-2xl font-bold text-white sm:text-3xl">
                  {PRODUCT_INFO.price}
                </span>
                <a
                  href={PRODUCT_INFO.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group relative inline-flex flex-1 items-center justify-center overflow-hidden whitespace-nowrap rounded-xl bg-gradient-to-br from-[#7C3AED] via-[#6366F1] to-[#4F46E5] px-6 py-2.5 text-base font-medium text-white shadow-md transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-indigo-500/25 active:translate-y-0 sm:flex-none"
                >
                  <span className="relative z-10">Order Now</span>
                  <div className="absolute inset-0 bg-gradient-to-br from-[#6366F1] via-[#4F46E5] to-[#7C3AED] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                </a>
              </div>
            </div>
          </div>
        );

      case 'floating':
        return (
          <div
            className={cn(
              'fixed bottom-6 right-6 z-50 overflow-hidden rounded-2xl bg-[#1A1F2E] shadow-lg transition-all duration-500',
              isHovered ? 'w-80' : 'w-48',
            )}
          >
            <div className="relative p-4">
              <div className="flex items-center gap-4">
                <div className="relative h-16 w-16 flex-shrink-0 overflow-hidden rounded-lg">
                  <Image
                    src={
                      isHovered
                        ? PRODUCT_INFO.images.secondary
                        : PRODUCT_INFO.images.primary
                    }
                    alt={PRODUCT_INFO.name}
                    fill
                    className="object-cover transition-transform duration-700 hover:scale-110"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-lg font-bold text-white">
                    {PRODUCT_INFO.name}
                  </h3>
                  <p className="text-sm text-gray-400">{PRODUCT_INFO.price}</p>
                </div>
              </div>
              <div
                className={cn(
                  'mt-4 transition-all duration-500',
                  isHovered ? 'opacity-100' : 'opacity-0',
                )}
              >
                <a
                  href={PRODUCT_INFO.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#6366F1] to-[#4F46E5] px-6 py-3 text-sm font-semibold text-white transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:shadow-indigo-500/25 active:scale-[0.98] active:duration-75"
                >
                  Order Now - Ships Worldwide
                </a>
              </div>
            </div>
          </div>
        );

      case 'category':
        return (
          <div className="relative overflow-hidden rounded-xl bg-[#1A1F2E] p-4 shadow-lg">
            <div className="absolute inset-0 bg-gradient-to-r from-[#1A1F2E]/90 to-transparent" />
            <div className="relative z-10 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="relative h-20 w-20 overflow-hidden rounded-lg">
                  <Image
                    src={
                      isHovered
                        ? PRODUCT_INFO.images.secondary
                        : PRODUCT_INFO.images.primary
                    }
                    alt={PRODUCT_INFO.name}
                    fill
                    className="object-cover transition-transform duration-700 hover:scale-110"
                  />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white">
                    Enhance your {category} experience
                  </h3>
                  <p className="text-sm text-gray-400">
                    {PRODUCT_INFO.name} - {PRODUCT_INFO.price}
                  </p>
                </div>
              </div>
              <a
                href={PRODUCT_INFO.url}
                target="_blank"
                rel="noopener noreferrer"
                className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#6366F1] to-[#4F46E5] px-6 py-3 text-sm font-semibold text-white transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:shadow-indigo-500/25 active:scale-[0.98] active:duration-75"
              >
                Order Now
              </a>
            </div>
          </div>
        );
    }
  };

  return (
    <div
      className={cn('group', className)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {renderContent()}
    </div>
  );
}
