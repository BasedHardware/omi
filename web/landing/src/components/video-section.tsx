'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Play } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';

gsap.registerPlugin(ScrollTrigger);

export function VideoSection() {
  const t = useTranslations('videoSection');
  const sectionRef = useRef<HTMLElement>(null);
  const videoRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(videoRef.current,
        { opacity: 0, scale: 0.88, borderRadius: '3rem' },
        {
          opacity: 1, scale: 1, borderRadius: '1.5rem', duration: 1.2, ease: 'power2.out',
          scrollTrigger: { trigger: sectionRef.current, start: 'top 75%', end: 'top 25%', scrub: 1 },
        },
      );
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="relative py-24 md:py-32 overflow-hidden">
      <div className="mx-auto max-w-5xl px-6">
        <div ref={videoRef} className="relative aspect-video rounded-3xl overflow-hidden border border-white/10 shadow-2xl shadow-black/50">
          <div className="absolute inset-0 bg-gradient-to-br from-[#1a2332] via-[#0f1923] to-bg-primary" />
          <div className="absolute inset-0 bg-gradient-to-tr from-brand/5 via-transparent to-brand/[0.03]" />
          <div className="absolute top-1/3 right-1/4 w-64 h-64 rounded-full bg-brand/10 blur-[100px]" />
          <div className="absolute bottom-1/4 left-1/3 w-48 h-48 rounded-full bg-white/[0.03] blur-[60px]" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Link href="#" className="group flex items-center justify-center w-20 h-20 rounded-full bg-white/10 border border-white/20 backdrop-blur-md hover:bg-white/20 transition-all hover:scale-105">
              <Play size={28} className="text-white ml-1" />
            </Link>
          </div>
          <div className="absolute bottom-0 inset-x-0 h-24 bg-gradient-to-t from-black/40 to-transparent" />
          <div className="absolute bottom-6 left-6">
            <span className="text-xs text-white/60">{t('watchHow')}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
