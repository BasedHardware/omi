'use client';

import { trustLogos } from '@/lib/config';

export function TrustBar() {
  return (
    <section className="py-10 border-y border-white/5">
      <p className="text-center text-text-tertiary text-sm mb-8">
        Trusted by 300,000+ professionals from
      </p>
      <div className="relative overflow-hidden">
        {/* Fade edges */}
        <div className="absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-bg-primary to-transparent z-10" />
        <div className="absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-bg-primary to-transparent z-10" />

        <div className="flex animate-scroll-left">
          {[...trustLogos, ...trustLogos].map((name, i) => (
            <div
              key={`${name}-${i}`}
              className="flex-shrink-0 mx-10 flex items-center justify-center"
            >
              <span className="text-text-tertiary/50 font-display font-semibold text-xl tracking-wide whitespace-nowrap">
                {name}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
