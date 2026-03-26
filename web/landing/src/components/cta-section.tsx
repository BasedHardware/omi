'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ArrowRight } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

export function CTASection() {
  const t = useTranslations('cta');
  const sectionRef = useRef<HTMLElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(cardRef.current,
        { opacity: 0, scale: 0.9, y: 40 },
        {
          opacity: 1, scale: 1, y: 0, duration: 1.2, ease: 'power3.out',
          scrollTrigger: { trigger: sectionRef.current, start: 'top 80%' },
        },
      );

      const glow = cardRef.current?.querySelector('.cta-glow');
      if (glow) {
        gsap.fromTo(glow,
          { scale: 0.8, opacity: 0 },
          {
            scale: 1.2, opacity: 0.5, duration: 2, ease: 'power1.inOut',
            scrollTrigger: { trigger: sectionRef.current, start: 'top 70%' },
          },
        );
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div ref={cardRef} className="relative rounded-3xl overflow-hidden border border-white/10 p-12 md:p-20 text-center">
          <div className="absolute inset-0 bg-gradient-to-br from-brand/10 via-brand/5 to-transparent" />
          <div className="cta-glow absolute top-0 right-0 w-96 h-96 bg-brand/10 rounded-full blur-[120px]" />
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-brand/5 rounded-full blur-[80px]" />

          <div className="relative z-10">
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4">
              {t('heading')}<br />{t('headingLine2')}
            </h2>
            <p className="text-text-tertiary text-lg max-w-md mx-auto mb-10">{t('description')}</p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href={brand.links.order} className="group flex items-center gap-2 bg-brand hover:bg-brand-dark text-white font-medium text-sm px-8 py-4 rounded-full transition-all hover:shadow-lg hover:shadow-brand/20">
                {t('orderNooto')} <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link href={brand.links.tryBrowser} className="text-text-secondary hover:text-white text-sm font-medium border border-white/10 px-8 py-4 rounded-full hover:border-white/20 transition-all">
                {t('tryFreeInBrowser')}
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
