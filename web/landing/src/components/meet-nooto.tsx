'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ArrowRight } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

export function MeetNooto() {
  const t = useTranslations('meetNooto');
  const sectionRef = useRef<HTMLElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(headerRef.current,
        { opacity: 0, y: 40, filter: 'blur(4px)' },
        { opacity: 1, y: 0, filter: 'blur(0px)', duration: 1, scrollTrigger: { trigger: headerRef.current, start: 'top 85%' } },
      );

      const cards = cardsRef.current?.querySelectorAll('.meet-card');
      if (cards) {
        gsap.fromTo(cards,
          { opacity: 0, y: 80, scale: 0.92 },
          {
            opacity: 1, y: 0, scale: 1, duration: 1, stagger: 0.2, ease: 'power3.out',
            scrollTrigger: { trigger: cardsRef.current, start: 'top 80%' },
          },
        );
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div ref={headerRef} className="text-center mb-16">
          <h2 className="font-display font-bold text-3xl md:text-5xl mb-6">
            {t('heading')} <strong>{brand.nameLower}</strong>
          </h2>
          <p className="text-text-tertiary text-lg max-w-lg mx-auto">{t('chooseDevice')}</p>
        </div>

        <div ref={cardsRef} className="grid md:grid-cols-2 gap-6">
          <ProductCard
            title={brand.name}
            subtitle={t('pendantSubtitle')}
            description={t('pendantDescription')}
            href={brand.links.product}
            accent="brand"
            learnMore={t('learnMore')}
          />
          <ProductCard
            title={`${brand.name} Glass`}
            subtitle={t('glassSubtitle')}
            description={t('glassDescription')}
            href={brand.links.glass}
            accent="white"
            learnMore={t('learnMore')}
          />
        </div>
      </div>
    </section>
  );
}

function ProductCard({ title, subtitle, description, href, accent, learnMore }: { title: string; subtitle: string; description: string; href: string; accent: string; learnMore: string }) {
  const isBrand = accent === 'brand';
  return (
    <Link href={href} className="meet-card group block">
      <div className={`relative rounded-3xl overflow-hidden border transition-all duration-500 ${isBrand ? 'border-brand/20 hover:border-brand/40 hover:shadow-lg hover:shadow-brand/10' : 'border-white/10 hover:border-white/20 hover:shadow-lg hover:shadow-white/5'}`}>
        <div className={`aspect-[4/3] flex items-center justify-center ${isBrand ? 'bg-gradient-to-br from-brand/10 via-brand/5 to-transparent' : 'bg-gradient-to-br from-white/[0.06] via-white/[0.03] to-transparent'}`}>
          <div className="relative">
            <div className={`w-28 h-28 md:w-36 md:h-36 rounded-full border flex items-center justify-center group-hover:scale-105 transition-transform duration-700 ${isBrand ? 'border-brand/30 bg-brand/10' : 'border-white/15 bg-white/5'}`}>
              <div className={`w-16 h-16 md:w-20 md:h-20 rounded-full border ${isBrand ? 'border-brand/40 bg-gradient-to-br from-brand/30 to-brand/10 shadow-[0_0_40px_rgba(59,130,246,0.15)]' : 'border-white/20 bg-gradient-to-br from-white/15 to-white/5'}`} />
            </div>
            <div className={`absolute inset-0 rounded-full blur-3xl opacity-20 ${isBrand ? 'bg-brand' : 'bg-white/20'}`} />
          </div>
        </div>
        <div className="p-6 md:p-8">
          <div className="text-xs text-text-tertiary uppercase tracking-widest mb-2">{subtitle}</div>
          <h3 className="font-display font-bold text-xl md:text-2xl mb-2">{title}</h3>
          <p className="text-text-tertiary text-sm leading-relaxed mb-4">{description}</p>
          <div className="flex items-center gap-2 text-sm font-medium text-brand group-hover:gap-3 transition-all">
            {learnMore} <ArrowRight size={16} />
          </div>
        </div>
      </div>
    </Link>
  );
}
