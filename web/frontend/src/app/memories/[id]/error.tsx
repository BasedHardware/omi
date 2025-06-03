'use client';

import { NavArrowLeft, Xmark, ArrowRight, Clock } from 'iconoir-react';
import Link from 'next/link';

export default function Error() {
  console.log('Memory not found');
  
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0B0F17] p-4 pt-32">
      <div className="mx-auto max-w-lg text-center">
        {/* Icon container with animation */}
        <div className="relative mb-8 inline-flex h-24 w-24 items-center justify-center">
          <div className="absolute inset-0 rounded-full bg-gradient-to-r from-red-500/20 to-orange-500/20 blur-xl" />
          <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
            <Xmark className="h-10 w-10 text-red-400 animate-pulse" />
          </div>
        </div>

        {/* Main heading */}
        <h1 className="mb-4 bg-gradient-to-r from-white to-zinc-400 bg-clip-text text-3xl font-bold text-transparent">
          Memory Not Found
        </h1>
        
        {/* Description */}
        <p className="mb-8 text-lg leading-relaxed text-zinc-400">
          Oops! The memory you're looking for seems to have vanished into the digital ether. 
          It might have been deleted, moved, or perhaps it never existed in the first place.
        </p>

        {/* Action button */}
        <div className="flex justify-center">
          <Link
            href="/apps"
            className="group flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 px-8 py-4 font-medium text-white shadow-lg transition-all duration-300 hover:scale-105 hover:shadow-purple-500/25"
          >
            <NavArrowLeft className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
            Back to Home
          </Link>
        </div>
      </div>

      {/* Subtle decorative elements */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-gradient-to-r from-purple-500/5 to-blue-500/5 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-gradient-to-r from-blue-500/5 to-purple-500/5 blur-3xl" />
      </div>
    </div>
  );
}
