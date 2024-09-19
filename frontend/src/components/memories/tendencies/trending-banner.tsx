'use client';
import getTrends from '@/src/actions/trends/get-trends';
import { Trend } from '@/src/types/trends/trends.types';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';
import { ArrowRight } from 'iconoir-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

export default function TrendingBanner() {
  const [trends, setTrends] = useState<Trend[]>([]);
  const [currentTrend, setCurrentTrend] = useState('');

  useEffect(() => {
    getTrends().then((res) => {
      setTrends(res);
    });
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      const randomIndex = Math.floor(Math.random() * trends.length);
      setCurrentTrend(trends[randomIndex]?.category ?? '');
    }, 3000);
    return () => clearInterval(interval);
  }, [trends]);

  return (
    <header className="sticky top-16 z-[40] w-full text-white md:hidden">
      <Link href={'/dreamforce'}>
        <div className="flex items-center justify-between bg-gradient-to-r from-[#030710] to-[#050c1b] px-4 py-3 shadow-md shadow-black/20 md:px-12">
          <h1>What's Trending</h1>
          <div className="flex items-center gap-2">
            {currentTrend && (
              <span
                key={currentTrend}
                className="animate-slideRightAndFade rounded-sm bg-[#5d5e77cc] px-1.5 py-0.5 text-xs text-white transition-all"
              >
                {capitalizeFirstLetter(currentTrend)}
              </span>
            )}
            <ArrowRight className="text-[10px]" />
          </div>
        </div>
      </Link>
    </header>
  );
}
