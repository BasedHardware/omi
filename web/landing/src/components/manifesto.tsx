'use client';

import { useRef, useEffect, useMemo } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useTranslations } from 'next-intl';

gsap.registerPlugin(ScrollTrigger);

interface Statement {
  heading: string;
  body: string;
  align: 'left' | 'center';
  headingSize: string;
}

const alignClasses = {
  left: 'items-start text-left pl-[8%] md:pl-[15%] pr-[8%]',
  center: 'items-center text-center px-8',
};

export function Manifesto() {
  const t = useTranslations('manifesto');

  const statements: Statement[] = useMemo(() => [
    {
      heading: t('statement1Heading'),
      body: t('statement1Body'),
      align: 'left',
      headingSize: 'text-[clamp(1.8rem,4vw,3rem)]',
    },
    {
      heading: t('statement2Heading'),
      body: t('statement2Body'),
      align: 'left',
      headingSize: 'text-[clamp(1.6rem,3.5vw,2.75rem)]',
    },
    {
      heading: t('statement3Heading'),
      body: t('statement3Body'),
      align: 'center',
      headingSize: 'text-[clamp(2rem,4.5vw,3.5rem)]',
    },
    {
      heading: t('statement4Heading'),
      body: t('statement4Body'),
      align: 'left',
      headingSize: 'text-[clamp(1.6rem,3.5vw,2.75rem)]',
    },
    {
      heading: t('statement5Heading'),
      body: t('statement5Body'),
      align: 'center',
      headingSize: 'text-[clamp(2.2rem,5vw,4rem)]',
    },
  ], [t]);

  const containerRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const counterRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    const cards = cardsRef.current;
    const progress = progressRef.current;
    const glow = glowRef.current;
    const heading = headingRef.current;
    const counter = counterRef.current;
    if (!container || !cards || !progress || !glow || !heading || !counter) return;

    const cardEls = cards.querySelectorAll<HTMLElement>('.manifesto-card');
    const totalCards = cardEls.length;
    const scrollDistance = window.innerHeight * (totalCards * 3 + 2);

    const ctx = gsap.context(() => {
      gsap.set(cardEls, { autoAlpha: 0 });

      const introWords = heading.querySelectorAll('.intro-word');
      gsap.set(introWords, { opacity: 0, y: 30, filter: 'blur(10px)' });

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: container,
          start: 'top top',
          end: `+=${scrollDistance}`,
          pin: true,
          scrub: 1.2,
          anticipatePin: 1,
        },
      });

      tl.to(introWords, {
        opacity: 1, y: 0, filter: 'blur(0px)', duration: 2, stagger: 0.3, ease: 'power3.out',
      });

      tl.to({}, { duration: 3 });

      tl.to(heading, {
        autoAlpha: 0, scale: 1.1, filter: 'blur(20px)', duration: 1.5, ease: 'power2.in',
      });

      cardEls.forEach((card, i) => {
        const s = statements[i];
        const p = card.querySelector('.card-p') as HTMLElement;
        const line = card.querySelector('.card-line') as HTMLElement;
        const words = card.querySelectorAll('.card-word');

        tl.call(() => {
          if (counter) counter.textContent = String(i + 1).padStart(2, '0');
        });

        tl.to(progress, { scaleY: (i + 1) / totalCards, duration: 2, ease: 'none' }, '<');

        const glowX = s.align === 'left' ? '-20%' : '0%';
        tl.to(glow, {
          x: glowX, y: `${Math.cos(i) * 10}%`, scale: 0.8 + (i % 3) * 0.3, duration: 3, ease: 'power1.inOut',
        }, '<');

        tl.to(card, { autoAlpha: 1, duration: 0.1 });
        tl.fromTo(line, { scaleX: 0 }, { scaleX: 1, duration: 1, ease: 'power2.inOut' });

        gsap.set(words, { opacity: 0, y: 20, filter: 'blur(8px)' });
        tl.to(words, {
          opacity: 1, y: 0, filter: 'blur(0px)', duration: 1.5, stagger: 0.15, ease: 'power3.out',
        }, '-=0.5');

        tl.fromTo(p, { opacity: 0, y: 15 }, {
          opacity: 1, y: 0, duration: 1.5, ease: 'power2.out',
        }, '-=1');

        tl.to({}, { duration: 4 });

        if (i < totalCards - 1) {
          tl.to(card, {
            autoAlpha: 0, scale: 0.95, filter: 'blur(12px)', y: -20, duration: 1.5, ease: 'power2.in',
          });
          tl.set(card, { filter: 'blur(0px)', scale: 1, y: 0 });
        }
      });

      tl.to({}, { duration: 2 });
    }, container);

    return () => ctx.revert();
  }, [statements]);

  const introHeading = t('introHeading');

  return (
    <section
      ref={containerRef}
      className="relative h-screen w-full overflow-hidden border-t border-white/5 bg-bg-primary"
    >
      <div
        ref={glowRef}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full bg-brand/[0.04] blur-[200px] pointer-events-none"
      />

      <div
        className="absolute inset-0 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.5) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <div className="absolute left-8 top-1/2 -translate-y-1/2 flex-col items-center gap-3 z-20 hidden lg:flex">
        <span
          ref={counterRef}
          className="font-display text-[11px] text-brand font-bold tracking-widest tabular-nums"
        >
          01
        </span>
        <div className="w-[2px] h-24 bg-white/[0.06] relative overflow-hidden rounded-full">
          <div
            ref={progressRef}
            className="absolute top-0 left-0 w-full bg-brand origin-top rounded-full"
            style={{ height: '100%', transform: 'scaleY(0)' }}
          />
        </div>
        <span className="font-display text-[11px] text-white/15 tracking-widest">
          {String(statements.length).padStart(2, '0')}
        </span>
      </div>

      <div
        ref={headingRef}
        className="absolute inset-0 flex items-center justify-center z-10"
      >
        <h2 className="font-display font-bold text-[clamp(2rem,5vw,4rem)] text-center leading-[1.1] px-6 max-w-4xl">
          {splitIntoWords(introHeading).map((word, i) => (
            <span key={i} className="intro-word inline-block mr-[0.3em]">
              {word}
            </span>
          ))}
          <span className="intro-word inline-block text-brand">{t('introHighlight')}</span>
        </h2>
      </div>

      <div ref={cardsRef} className="absolute inset-0 z-10">
        {statements.map((s, i) => (
          <div
            key={i}
            className={`manifesto-card absolute inset-0 flex flex-col justify-center ${alignClasses[s.align]}`}
          >
            <div className="max-w-5xl">
              <div
                className={`card-line h-[2px] bg-brand mb-6 ${s.align === 'center' ? 'w-12 mx-auto origin-center' : 'w-16 origin-left'}`}
                style={{ transform: 'scaleX(0)' }}
              />
              <h3 className={`card-h font-display font-bold ${s.headingSize} leading-[1.12] mb-4`}>
                {splitIntoWords(s.heading).map((word, j) => (
                  <span key={j} className="card-word inline-block mr-[0.25em]">
                    {word}
                  </span>
                ))}
              </h3>
              <p className={`card-p text-text-tertiary text-base md:text-lg leading-relaxed ${s.align === 'center' ? 'max-w-2xl mx-auto' : 'max-w-2xl'}`}>
                {s.body}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="absolute top-10 right-10 w-14 h-14 border-t border-r border-white/[0.04] rounded-tr-2xl pointer-events-none hidden lg:block" />
      <div className="absolute bottom-10 left-10 w-14 h-14 border-b border-l border-white/[0.04] rounded-bl-2xl pointer-events-none hidden lg:block" />
    </section>
  );
}

function splitIntoWords(text: string): string[] {
  return text.split(' ');
}
