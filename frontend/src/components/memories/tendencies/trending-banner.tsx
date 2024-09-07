'use client';

import { ArrowRight } from "iconoir-react";
import { useEffect, useState } from "react";

const topTrending = [
  {
    title: "Work",
    count: 23,
    ranking: 1
  },
  {
    title: "Business",
    count: 6,
    ranking: 2
  },
  {
    title: "Inspiration",
    count: 6,
    ranking: 3
  },
  {
    title: "Social",
    count: 6
  }
]

export default function TrendingBanner() {
  const [currentTrend, setCurrentTrend] = useState(topTrending[0]);

  useEffect(() => {
    const interval = setInterval(() => {
      const randomIndex = Math.floor(Math.random() * topTrending.length);
      setCurrentTrend(topTrending[randomIndex]);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return(
    <header className="sticky md:hidden top-16 w-full z-[40] text-white">
      <div className="flex items-center shadow-md shadow-black/20 justify-between px-4 md:px-12 py-3 bg-gradient-to-r from-[#030710] to-[#050c1b]">
        <h1>What's Trending</h1>
        <div className="flex gap-2 items-center">
          <span key={currentTrend.title} className="animate-slideRightAndFade transition-all bg-[#5d5e77cc] text-white px-1.5 rounded-sm text-xs py-0.5">{currentTrend.title}</span>
          <ArrowRight className="text-[10px]"/>
        </div>
      </div>
    </header>
  )
}