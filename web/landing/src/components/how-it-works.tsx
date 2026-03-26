'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Mic, Brain, ListChecks } from 'lucide-react';
import { useTranslations } from 'next-intl';

gsap.registerPlugin(ScrollTrigger);

export function HowItWorks() {
  const t = useTranslations('howItWorks');
  const sectionRef = useRef<HTMLElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);

  const steps = [
    { icon: Mic, step: '01', title: t('step1Title'), description: t('step1Description') },
    { icon: Brain, step: '02', title: t('step2Title'), description: t('step2Description') },
    { icon: ListChecks, step: '03', title: t('step3Title'), description: t('step3Description') },
  ];

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(headerRef.current,
        { opacity: 0, y: 40, filter: 'blur(4px)' },
        {
          opacity: 1, y: 0, filter: 'blur(0px)', duration: 1,
          scrollTrigger: { trigger: headerRef.current, start: 'top 85%' },
        },
      );

      const cards = cardsRef.current?.querySelectorAll('.hiw-card');
      if (cards) {
        gsap.fromTo(cards,
          { opacity: 0, y: 60, scale: 0.95 },
          {
            opacity: 1, y: 0, scale: 1, duration: 0.8, stagger: 0.15, ease: 'power3.out',
            scrollTrigger: { trigger: cardsRef.current, start: 'top 80%' },
          },
        );

        const lines = cardsRef.current?.querySelectorAll('.hiw-line');
        if (lines) {
          gsap.fromTo(lines,
            { scaleX: 0 },
            {
              scaleX: 1, duration: 0.6, stagger: 0.15, ease: 'power2.inOut',
              scrollTrigger: { trigger: cardsRef.current, start: 'top 70%' },
            },
          );
        }
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div ref={headerRef} className="text-center mb-20">
          <h2 className="font-display font-bold text-3xl md:text-5xl mb-4">{t('heading')}</h2>
          <p className="text-text-tertiary text-lg max-w-lg mx-auto">{t('description')}</p>
        </div>

        <div ref={cardsRef} className="grid md:grid-cols-3 gap-8 md:gap-12">
          {steps.map((step, i) => (
            <div key={step.title} className="hiw-card relative text-center md:text-left">
              <div className="text-5xl font-display font-bold text-white/[0.04] mb-4">{step.step}</div>
              <div className="w-14 h-14 rounded-2xl bg-brand/10 border border-brand/20 flex items-center justify-center mb-5 mx-auto md:mx-0">
                <step.icon size={24} className="text-brand" />
              </div>
              <h3 className="font-display font-semibold text-xl mb-3">{step.title}</h3>
              <p className="text-text-tertiary text-sm leading-relaxed">{step.description}</p>
              {i < steps.length - 1 && (
                <div className="hiw-line hidden md:block absolute top-10 -right-6 w-12 h-px bg-gradient-to-r from-white/10 to-transparent origin-left" />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
