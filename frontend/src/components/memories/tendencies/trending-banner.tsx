'use client';

import { ArrowRight } from 'iconoir-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

const topTrending = [
  {
    title: 'Work',
    count: 23,
    ranking: 1,
  },
  {
    title: 'Business',
    count: 6,
    ranking: 2,
  },
  {
    title: 'Inspiration',
    count: 6,
    ranking: 3,
  },
  {
    title: 'Social',
    count: 6,
  },
];

export default function TrendingBanner() {
  const [currentTrend, setCurrentTrend] = useState(topTrending[0]);

  useEffect(() => {
    const interval = setInterval(() => {
      const randomIndex = Math.floor(Math.random() * topTrending.length);
      setCurrentTrend(topTrending[randomIndex]);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-16 z-[40] w-full text-white md:hidden">
      <Link href={'/dreamforce'}>
        <div className="flex items-center justify-between bg-gradient-to-r from-[#030710] to-[#050c1b] px-4 py-3 shadow-md shadow-black/20 md:px-12">
          <h1>What's Trending</h1>
          <div className="flex items-center gap-2">
            <span
              key={currentTrend.title}
              className="animate-slideRightAndFade rounded-sm bg-[#5d5e77cc] px-1.5 py-0.5 text-xs text-white transition-all"
            >
              {currentTrend.title}
            </span>
            <ArrowRight className="text-[10px]" />
          </div>
        </div>
      </Link>
    </header>
  );
}
