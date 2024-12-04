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
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#1A1F2E] to-[#141824] p-1">
            <div className="animate-gradient-x absolute inset-0 bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10" />
            <div className="relative backdrop-blur-sm backdrop-filter">
              <div className="relative z-10 grid grid-cols-1 gap-6 p-6 sm:grid-cols-[1fr,auto] sm:gap-8 md:p-8">
                {/* Left Content */}
                <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
                  {/* Image Container */}
                  <div className="group relative h-24 w-24 flex-shrink-0 sm:h-36 sm:w-36">
                    <div className="absolute -inset-0.5 rounded-2xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 opacity-75 blur-sm transition-opacity duration-500 group-hover:opacity-100" />
                    <div className="relative h-full w-full overflow-hidden rounded-2xl">
                      <Image
                        src={
                          isHovered
                            ? PRODUCT_INFO.images.secondary
                            : PRODUCT_INFO.images.primary
                        }
                        alt={PRODUCT_INFO.name}
                        fill
                        className="object-cover transition-all duration-700 group-hover:scale-110"
                      />
                    </div>
                  </div>

                  {/* Text Content */}
                  <div className="space-y-4">
                    <div>
                      <h3 className="bg-gradient-to-r from-white via-white to-white/75 bg-clip-text text-2xl font-bold text-transparent sm:text-3xl">
                        Experience {appName} with {PRODUCT_INFO.name}
                      </h3>
                      <p className="mt-2 text-base text-gray-400 sm:text-lg">
                        AI-Powered Voice Assistant - {PRODUCT_INFO.shipping}
                      </p>
                    </div>

                    {/* Features */}
                    <div className="flex flex-wrap gap-3">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/10 px-3 py-1 text-sm text-cyan-300">
                        <svg
                          className="h-3.5 w-3.5"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z" />
                          <path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z" />
                        </svg>
                        Second Brain
                      </span>
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-500/10 px-3 py-1 text-sm text-purple-300">
                        <svg
                          className="h-3.5 w-3.5"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path d="M5.5 16a3.5 3.5 0 01-.369-6.98 4 4 0 117.753-1.977A4.5 4.5 0 1113.5 16h-8z" />
                        </svg>
                        Voice AI
                      </span>
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-teal-500/10 px-3 py-1 text-sm text-teal-300">
                        <svg
                          className="h-3.5 w-3.5"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M3 5a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-2.22l.123.489.804.804A1 1 0 0113 18H7a1 1 0 01-.707-1.707l.804-.804L7.22 15H5a2 2 0 01-2-2V5zm5.771 7H5V5h10v7H8.771z"
                            clipRule="evenodd"
                          />
                        </svg>
                        Built-in Memory
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right Content - Price and CTA */}
                <div className="flex flex-col items-center gap-4 sm:items-end">
                  <div className="text-center sm:text-right">
                    <div className="flex items-center gap-2 sm:justify-end">
                      <span className="text-3xl font-bold text-white sm:text-4xl">
                        {PRODUCT_INFO.price}
                      </span>
                      <span className="rounded-full bg-green-500/10 px-2.5 py-1 text-sm text-green-300">
                        Shipping Now
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-gray-400">
                      30-day money-back guarantee
                    </p>
                  </div>

                  <a
                    href={PRODUCT_INFO.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group relative inline-flex items-center justify-center overflow-hidden rounded-xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 p-0.5 transition-all duration-300 ease-out hover:bg-gradient-to-br hover:shadow-lg hover:shadow-indigo-500/25"
                  >
                    <span className="relative inline-flex items-center gap-2 rounded-[0.625rem] bg-[#1A1F2E] px-6 py-3 text-base font-medium text-white transition-all duration-300 group-hover:bg-opacity-90 sm:text-lg">
                      <span>Order Now</span>
                      <svg
                        className="h-5 w-5 transition-transform duration-300 group-hover:translate-x-1"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          d="M13 7l5 5m0 0l-5 5m5-5H6"
                        />
                      </svg>
                    </span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        );

      case 'floating':
        return (
          <div
            className={cn(
              'fixed bottom-6 right-6 z-50 overflow-hidden rounded-2xl bg-gradient-to-br from-[#1A1F2E] to-[#141824] p-1 shadow-lg transition-all duration-500',
              isHovered ? 'w-80' : 'w-48',
            )}
          >
            <div className="animate-gradient-x absolute inset-0 bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10" />
            <div className="relative backdrop-blur-sm backdrop-filter">
              <div className="p-4">
                <div className="flex items-center gap-4">
                  <div className="group relative h-16 w-16 flex-shrink-0 overflow-hidden rounded-xl">
                    <div className="absolute -inset-0.5 rounded-xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 opacity-75 blur-sm transition-opacity duration-500 group-hover:opacity-100" />
                    <div className="relative h-full w-full overflow-hidden rounded-xl">
                      <Image
                        src={
                          isHovered
                            ? PRODUCT_INFO.images.secondary
                            : PRODUCT_INFO.images.primary
                        }
                        alt={PRODUCT_INFO.name}
                        fill
                        className="object-cover transition-all duration-700 group-hover:scale-110"
                      />
                    </div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-lg font-bold text-white">
                      {PRODUCT_INFO.name}
                    </h3>
                    <div className="flex items-center gap-2">
                      <p className="text-sm text-gray-400">{PRODUCT_INFO.price}</p>
                      <span className="rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-300">
                        Shipping Now
                      </span>
                    </div>
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
                    className="group relative inline-flex w-full items-center justify-center overflow-hidden rounded-xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 p-0.5 transition-all duration-300 ease-out hover:bg-gradient-to-br hover:shadow-lg hover:shadow-indigo-500/25"
                  >
                    <span className="relative inline-flex w-full items-center justify-center gap-2 rounded-[0.625rem] bg-[#1A1F2E] px-4 py-2 text-sm font-medium text-white transition-all duration-300 group-hover:bg-opacity-90">
                      <span>Order Now</span>
                      <svg
                        className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          d="M13 7l5 5m0 0l-5 5m5-5H6"
                        />
                      </svg>
                    </span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        );

      case 'category':
        return (
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#1A1F2E] to-[#141824] p-1">
            <div className="animate-gradient-x absolute inset-0 bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10" />
            <div className="relative backdrop-blur-sm backdrop-filter">
              <div className="relative z-10 flex flex-wrap items-center justify-between gap-4 p-4 sm:flex-nowrap sm:gap-6 sm:p-6">
                <div className="flex items-center gap-4">
                  <div className="group relative h-16 w-16 flex-shrink-0 overflow-hidden rounded-xl sm:h-20 sm:w-20">
                    <div className="absolute -inset-0.5 rounded-xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 opacity-75 blur-sm transition-opacity duration-500 group-hover:opacity-100" />
                    <div className="relative h-full w-full overflow-hidden rounded-xl">
                      <Image
                        src={
                          isHovered
                            ? PRODUCT_INFO.images.secondary
                            : PRODUCT_INFO.images.primary
                        }
                        alt={PRODUCT_INFO.name}
                        fill
                        className="object-cover transition-all duration-700 group-hover:scale-110"
                      />
                    </div>
                  </div>
                  <div>
                    <h3 className="bg-gradient-to-r from-white via-white to-white/75 bg-clip-text text-lg font-bold text-transparent sm:text-xl">
                      Enhance your {category} experience
                    </h3>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <p className="text-sm text-gray-400 sm:text-base">
                        {PRODUCT_INFO.name} - {PRODUCT_INFO.price}
                      </p>
                      <span className="rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-300 sm:text-sm">
                        Shipping Now
                      </span>
                    </div>
                  </div>
                </div>
                <a
                  href={PRODUCT_INFO.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group relative inline-flex items-center justify-center overflow-hidden rounded-xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 p-0.5 transition-all duration-300 ease-out hover:bg-gradient-to-br hover:shadow-lg hover:shadow-indigo-500/25"
                >
                  <span className="relative inline-flex items-center gap-2 rounded-[0.625rem] bg-[#1A1F2E] px-4 py-2 text-sm font-medium text-white transition-all duration-300 group-hover:bg-opacity-90 sm:px-6 sm:py-3">
                    <span>Order Now</span>
                    <svg
                      className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1 sm:h-5 sm:w-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M13 7l5 5m0 0l-5 5m5-5H6"
                      />
                    </svg>
                  </span>
                </a>
              </div>
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
