'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Smartphone, LayoutGrid } from 'lucide-react';
import Link from 'next/link';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

const features = [
  {
    icon: Smartphone,
    title: 'Works with every device',
    description: `${brand.name} App works seamlessly with your existing device — no need to buy anything new!`,
    cta: { label: 'Integrate your device', href: brand.links.integrations },
  },
  {
    icon: LayoutGrid,
    title: 'Thousands of Apps',
    description: 'Apps for Productivity, Relationships, Health, Companionship and more — all on one device.',
    cta: { label: 'Browse apps', href: brand.links.apps },
  },
];

export function Features() {
  const sectionRef = useRef<HTMLElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const cards = cardsRef.current?.querySelectorAll('.feat-card');
      if (cards) {
        gsap.fromTo(cards,
          { opacity: 0, y: 60, rotateX: 4 },
          {
            opacity: 1, y: 0, rotateX: 0, duration: 0.9, stagger: 0.15, ease: 'power3.out',
            scrollTrigger: { trigger: cardsRef.current, start: 'top 80%' },
          },
        );
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-16 md:py-24" style={{ perspective: '1200px' }}>
      <div className="mx-auto max-w-7xl px-6">
        <div ref={cardsRef} className="grid md:grid-cols-2 gap-6">
          {features.map((feature) => (
            <div key={feature.title} className="feat-card group bg-bg-secondary border border-white/10 rounded-2xl p-8 md:p-10 hover:border-brand/30 transition-all duration-500 hover:shadow-lg hover:shadow-brand/5">
              <div className="w-12 h-12 rounded-xl bg-brand/10 flex items-center justify-center mb-5">
                <feature.icon size={24} className="text-brand" />
              </div>
              <h3 className="font-display font-bold text-xl md:text-2xl mb-3">{feature.title}</h3>
              <p className="text-text-tertiary text-sm leading-relaxed mb-6">{feature.description}</p>
              <Link href={feature.cta.href} className="inline-flex items-center gap-2 text-brand text-sm font-medium hover:underline group-hover:gap-3 transition-all">
                {feature.cta.label} <span>→</span>
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
